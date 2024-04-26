#include<windows.h>
#pragma comment( linker, "/subsystem:\"windows\" /entry:\"mainCRTStartup\"" )

int main()
{
	ShellExecute(NULL, L"open", L"run.bat", NULL, NULL, SW_HIDE);
	ShellExecute(NULL, L"open", L"dwrg.lnk", NULL, NULL, SW_SHOWMAXIMIZED);
}