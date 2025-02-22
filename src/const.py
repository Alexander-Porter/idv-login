manual_login_channels = [
    {
        "name": "小米账号",
        "channel": "xiaomi_app",
    },
    {"name": "华为账号", "channel": "huawei"},
    {"name": "vivo账号", "channel": "nearme_vivo"},
    {"name": "应用宝（微信）", "channel": "myapp"},
]


html = r"""<!DOCTYPE html>
<html lang="zh-cn">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>渠道服账号</title>
    
    <script src="https://lf9-cdn-tos.bytecdntp.com/cdn/expire-1-y/sweetalert/2.1.2/sweetalert.min.js"></script>
    <link href="https://lf26-cdn-tos.bytecdntp.com/cdn/expire-1-y/bootstrap/5.1.3/css/bootstrap.css" rel="stylesheet">
    <script src="https://lf3-cdn-tos.bytecdntp.com/cdn/expire-1-y/bootstrap/5.1.3/js/bootstrap.bundle.min.js"></script>
</head>

<body>
    <div class="container">
        <h1>渠道服账号</h1>
        <div>
            <select id="channelSelect"></select>
            <button onclick="manual()">手动登录</button>
            <p>当前自动登录账号：<strong id="default">Empty</strong></p>
            <button onclick="clearDefault()">清除自动登录</button>
            <button id="autoCloseBtn" onclick="switchAutoClose()">登录后自动关闭工具：加载中...</button>
        </div>
        <table class="table table-striped">
            <thead>
                <tr>
                    <th scope="col">选择</th>
                    <th scope="col">UUID</th>
                    <th scope="col">名称</th>
                    <th scope="col">上次登录</th>
                    <th scope="col">操作</th>
                </tr>
            </thead>
            <tbody id="channelTableBody">
                <!-- 账号记录将在这里显示 -->
            </tbody>
        </table>
    </div>

    
    <script>
        function timeStampToLocalTime(timestamp) {
            return new Date(timestamp * 1000).toLocaleString();
        };
        function renameChannel(uuid) {
            var newName = prompt("请输入新的账号名称");
            if (newName) {
                fetch(`/_idv-login/rename?uuid=${uuid}&new_name=${newName}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            swal('账号已成功改名');
                            location.reload();
                        } else {
                            swal('改名失败');
                        }
                    });
            }
        }

        function deleteChannel(uuid) {
            var confirmDelete = confirm("确定要删除这个账号吗？");
            if (confirmDelete) {
                fetch(`/_idv-login/del?uuid=${uuid}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            swal('账号已成功删除');
                            location.reload();
                        } else {
                            swal('删除失败');
                        }
                    });
            }
        }

        function switchChannel(uuid) {
            fetch(`/_idv-login/switch?uuid=${uuid}`)
                .then(response => response.json())
                .then(data => {
                    if (data.current == uuid) {
                        swal('模拟登录成功');
                        location.reload();
                    } else {
                        swal('写登录失败');
                    }
                });
        }
        function defaultChannel(uuid) {
            game_id = getQueryVariable("game_id");
            fetch(`/_idv-login/setDefault?uuid=${uuid}&game_id=${game_id}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        swal('设置默认成功');
                        location.reload();
                    } else {
                        swal('写登录失败');
                    }
                });
        }

        function clearDefault() {
            game_id = getQueryVariable("game_id");
            fetch(`/_idv-login/clearDefault?game_id=${game_id}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        swal('清除默认成功');
                        location.reload();
                    } else {
                        swal('清除失败');
                    }
                });
        }

        function getQueryVariable(variable) {
            var query = window.location.search.substring(1);
            var vars = query.split("&");
            for (var i = 0; i < vars.length; i++) {
                var pair = vars[i].split("=");
                if (pair[0] == variable) { return pair[1]; }
            }
            return ("");
        }
        // 在页面加载时获取账号列表
        window.onload = function () {
            //获得query参数game_id
            game_id = getQueryVariable("game_id");
            fetch('/_idv-login/list?game_id=' + game_id)
                .then(response => response.json())
                .then(data => {
                    var tableBody = document.getElementById('channelTableBody');
                    data.forEach(channel => {
                        var row = tableBody.insertRow();
                        row.insertCell().innerHTML = `<input type="checkbox" value="${channel.uuid}">`;
                        row.insertCell().innerHTML = channel.uuid;
                        row.insertCell().innerHTML = channel.name;
                        row.insertCell().innerHTML = timeStampToLocalTime(channel.last_login_time);
                        var actionsCell = row.insertCell();
                        actionsCell.innerHTML = `
                            <button onclick="switchChannel('${channel.uuid}')">登录</button>
                            <button onclick="renameChannel('${channel.uuid}')">改名</button>
                            <button onclick="deleteChannel('${channel.uuid}')">删除</button>
                            <button onclick="defaultChannel('${channel.uuid}')">设为自动登录</button>
                        `;
                    });
                });

            fetch('/_idv-login/manualChannels')
                .then(response => response.json())
                .then(data => {
                    var channelSelect = document.getElementById('channelSelect');
                    data.forEach(channel => {
                        var option = document.createElement('option');
                        option.value = channel.channel;
                        option.text = channel.name;
                        channelSelect.appendChild(option);
                    });
                });

            fetch('/_idv-login/defaultChannel?game_id=' + game_id)
                .then(response => response.json())
                .then(data => {
                    if (data.uuid != "") {
                        document.getElementById('default').innerText = data.uuid;
                    }
                });

            // 获取自动关闭状态
            fetch(`/_idv-login/get-auto-close-state?game_id=${game_id}`)
                .then(response => response.json())
                .then(data => {
                    if(data.success) {
                        updateAutoCloseButton(data.state);
                    }
                });
        }

        // 添加新的函数
        function updateAutoCloseButton(state) {
            const btn = document.getElementById('autoCloseBtn');
            btn.textContent = `登录后自动关闭工具：${state ? '开启' : '关闭'}`;
            btn.className = state ? 'btn btn-success' : 'btn btn-secondary';
        }

        function switchAutoClose() {
            game_id = getQueryVariable("game_id");
            fetch(`/_idv-login/switch-auto-close-state?game_id=${game_id}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateAutoCloseButton(data.state);
                        swal(data.state ? '已开启自动关闭' : '已关闭自动关闭');
                    } else {
                        swal('切换状态失败');
                    }
                });
        }
        function manual() {
            //获取channelSelect的值
            var selectedChannel = document.getElementById('channelSelect').value;
            
            fetch(`/_idv-login/import?channel=${selectedChannel}&game_id=${game_id}`)
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    swal('执行成功');
                                    location.reload();
                                } else {
                                    swal('执行失败，请检查工具日志');
                                }
                            });

        }
    </script>
</body>

</html>"""
