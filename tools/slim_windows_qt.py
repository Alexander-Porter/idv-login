"""Trim a *staged copy* of the Windows Qt wheels, not the cached interpreter.

Build-only dependency: pefile==2024.8.26. No target Windows code is executed.
The policy describes the Widgets/WebEngine application in src, not every Qt
feature. Re-audit it when the application's Qt usage changes.
"""

import argparse
import ast
from importlib import metadata
import json
from pathlib import Path
import re

import pefile


AUDITED_IMPORTS = {
    "QtCore", "QtGui", "QtNetwork", "QtWidgets",
    "QtWebEngineCore", "QtWebEngineWidgets",
}
# These are loaded dynamically and consequently are not PE import edges.
PLUGINS = {
    "platforms/qwindows.dll",                 # QApplication on Windows
    "styles/qmodernwindowsstyle.dll",          # default Windows widget style
    "imageformats/qico.dll",                   # configure_application_icon
    "tls/qschannelbackend.dll",                # QtNetwork's native TLS backend
    "networkinformation/qnetworklistmanager.dll",  # QtNetwork on Windows
}
RENDERER_SUPPORT = {"opengl32sw.dll", "d3dcompiler_47.dll"}
RESOURCES = {
    "icudtl.dat", "qtwebengine_resources.pak",
    "qtwebengine_resources_100p.pak", "qtwebengine_resources_200p.pak",
    "v8_context_snapshot.bin",
}


def source_imports(source_root):
    modules = set()
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = (["PyQt6." + item.name for item in node.names]
                         if node.module == "PyQt6" else [node.module or ""])
            else:
                continue
            modules.update(name.split(".")[1] for name in names
                           if name.startswith("PyQt6."))
    if modules != AUDITED_IMPORTS:
        raise RuntimeError(f"Qt usage changed; re-audit the packaging policy: {sorted(modules)}")
    return modules


def binding_closure(qt_root, direct):
    # SIP imports are Python binding dependencies, distinct from DLL imports.
    # WebEngineWidgets needs QtPrintSupport; WebEngineCore needs QtWebChannel.
    pending, modules = list(direct), set()
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        modules.add(name)
        sip = qt_root / "bindings" / name / f"{name}mod.sip"
        text = sip.read_text(encoding="utf-8-sig")
        pending.extend(re.findall(r"^%Import\s+(\w+)/", text, re.MULTILINE))
    return modules


def pe_closure(qt_root, seeds):
    binaries = {path.name.lower(): path for path in (qt_root / "Qt6/bin").iterdir()
                if path.suffix.lower() in {".dll", ".exe"}}
    pending, keep, edges = list(seeds), set(), {}
    while pending:
        path = pending.pop()
        if path in keep:
            continue
        if not path.is_file():
            raise FileNotFoundError(path)
        keep.add(path)
        with pefile.PE(str(path), fast_load=True) as pe:
            pe.parse_data_directories(directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ])
            imports = sorted({entry.dll.decode("ascii").lower()
                              for kind in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                              for entry in getattr(pe, kind, [])})
        edges[path.relative_to(qt_root).as_posix()] = imports
        for name in imports:
            if name in binaries:
                pending.append(binaries[name])
            elif name.startswith("qt6"):
                raise RuntimeError(f"Missing Qt dependency {name} required by {path.name}")
    return keep, edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-root", required=True, type=Path)
    parser.add_argument("--source-root", default=Path("src"), type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="remove unused files in this staged copy")
    args = parser.parse_args()
    root = args.qt_root.resolve()
    if root.name != "PyQt6" or args.qt_root.is_symlink():
        raise ValueError("--qt-root must be the staged PyQt6 directory")
    before = {path: path.stat().st_size for path in root.rglob("*") if path.is_file()}
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("Symlinks are not expected in Windows wheels")
    direct = source_imports(args.source_root)
    modules = binding_closure(root, direct)
    seeds = {root / f"{name}.pyd" for name in modules}
    seeds.update(root.glob("sip*.pyd"))
    seeds.update(root / "Qt6/plugins" / name for name in PLUGINS)
    seeds.update(root / "Qt6/bin" / name for name in RENDERER_SUPPORT | {"QtWebEngineProcess.exe"})
    keep, edges = pe_closure(root, seeds)
    keep.update({root / "__init__.py", root / "Qt6/bin/qt.conf"})
    keep.update(root / "Qt6/resources" / name for name in RESOURCES)
    # WebEngine selects its locale from QLocale (the user's OS), not from the
    # page's HTTP Accept-Language. All these locales are reachable today.
    locales = set((root / "Qt6/translations/qtwebengine_locales").glob("*.pak"))
    if not locales or not any(path.name == "en-US.pak" for path in locales):
        raise RuntimeError("WebEngine locale data is missing")
    keep.update(locales)
    missing = keep - before.keys()
    if missing:
        raise RuntimeError(f"Required Qt files missing: {sorted(str(p) for p in missing)}")
    removed = before.keys() - keep
    versions = {dist.metadata["Name"]: dist.version
                for dist in metadata.distributions(path=[str(root.parent)])
                if dist.metadata["Name"].lower().startswith("pyqt6")}
    report = {
        "applied": args.apply,
        "versions": dict(sorted(versions.items())),
        "direct_modules": sorted(direct), "binding_modules": sorted(modules),
        "before_bytes": sum(before.values()),
        "after_bytes": sum(before[path] for path in keep),
        "saved_bytes": sum(before[path] for path in removed),
        "kept_files": sorted(path.relative_to(root).as_posix() for path in keep),
        "removed_files": {path.relative_to(root).as_posix(): before[path]
                          for path in sorted(removed)},
        "pe_imports": edges,
    }
    # Calculate and validate the entire plan before deleting any staged file.
    if args.apply:
        for path in removed:
            path.unlink()
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Qt payload: {report['before_bytes']:,} -> {report['after_bytes']:,} bytes "
          f"({report['saved_bytes']:,} removed; applied={args.apply})")


if __name__ == "__main__":
    main()
