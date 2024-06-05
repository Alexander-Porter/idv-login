manual_login_channels = [
    {
        "name": "小米账号",
        "channel": "xiaomi_app",
    }
]


html = r"""<!DOCTYPE html>
<html lang="zh-cn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>渠道服账号</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container">
        <h1>渠道服账号</h1>
        <div>
            <select id="channelSelect"></select>
            <button onclick="mannual()">手动登录</button>
        </div>
        <table class="table table-striped">
            <thead>
                <tr>
                    <th scope="col">选择</th>
                    <th scope="col">UUID</th>
                    <th scope="col">名称</th>
                    <th scope="col">操作</th>
                </tr>
            </thead>
            <tbody id="channelTableBody">
                <!-- 账号记录将在这里显示 -->
            </tbody>
        </table>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function mannual() {
        //获取channelSelect的值
        var selectedChannel = document.getElementById('channelSelect').value;
        if (selectedChannel == 'xiaomi_app') {
            alert("请登录成功后，提示[找不到页面]后，复制浏览器地址栏里的网址(https://game.xiaomi.com/oauthcallback/mioauth?code=xxxxx)，程序会自动读取登录凭证！\n如果需要切换账号，在新打开的网页里点击右上角头像-》退出登录后再执行函数！");
        }
        //向服务器发送请求
        fetch(`/_idv-login/import?channel=${selectedChannel}`)
            .then(response => response.json())
            .then(data => {
              if (data.success) {
                alert('执行成功');
                location.reload();
              } else {
                alert('执行失败');
              }
            });
        }
        function renameChannel(uuid) {
            var newName = prompt("请输入新的账号名称");
            if (newName) {
                fetch(`/_idv-login/rename?uuid=${uuid}&new_name=${newName}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('账号已成功改名');
                            location.reload();
                        } else {
                            alert('改名失败');
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
                            alert('账号已成功删除');
                            location.reload();
                        } else {
                            alert('删除失败');
                        }
                    });
            }
        }
        function switchChannel(uuid) {
            fetch(`/_idv-login/switch?uuid=${uuid}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.current==uuid) {
                            alert('模拟登录成功');
                            location.reload();
                        } else {
                            alert('写登录失败失败');
                        }
                    });
        }

        function getQueryVariable(variable)
             {
       var query = window.location.search.substring(1);
       var vars = query.split("&");
       for (var i=0;i<vars.length;i++) {
               var pair = vars[i].split("=");
               if(pair[0] == variable){return pair[1];}
       }
       return (false);
            }
        // 在页面加载时获取账号列表
        window.onload = function() {
        //获得query参数game_id
        var game_id = getQueryVariable("game_id");
            fetch('/_idv-login/list?game_id='+game_id)
                .then(response => response.json())
                .then(data => {
                    var tableBody = document.getElementById('channelTableBody');
                    data.forEach(channel => {
                        var row = tableBody.insertRow();
                        row.insertCell().innerHTML = `<input type="checkbox" value="${channel.uuid}">`;
                        row.insertCell().innerHTML = channel.uuid;
                        row.insertCell().innerHTML = channel.name;
                        var actionsCell = row.insertCell();
                        actionsCell.innerHTML = `
                            <button onclick="switchChannel('${channel.uuid}')">登录</button>
                            <button onclick="renameChannel('${channel.uuid}')">改名</button>
                            <button onclick="deleteChannel('${channel.uuid}')">删除</button>
                        `;
                    });
                });

            fetch('/_idv-login/mannualChannels')
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
        }

        function executeFunction() {
            var selectedChannel = document.getElementById('channelSelect').value;
            fetch(`/_idv-login/import?channel=${selectedChannel}`)
                .then(response => response.json())
                .then(data => {
                    // 处理返回的数据
                });
        }
    </script>
</body>
</html>"""
