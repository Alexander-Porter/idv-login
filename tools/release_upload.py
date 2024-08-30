import sys
import requests
import os.path
import json
import traceback
from requests_toolbelt.multipart import encoder

#读取环境变量
secret_upload_pre_url=os.getenv("UPLOAD_PRE_URL")
secret_upload_url=os.getenv("UPLOAD_URL")
github_token=os.getenv("GITHUB_TOKEN")

def uploadFile(filePath):
    ext=filePath.split(".")[-1]
    fileName= os.path.split(filePath)[1]
    headers={"Connection":"keep-alive","sec-ch-ua":"\"Microsoft Edge\";v=\"105\", \" Not;A Brand\";v=\"99\", \"Chromium\";v=\"105\"","Accept":"application/json, text/plain, */*","armadaProductId":"hsc_push","sec-ch-ua-mobile":"?0","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27","token":"[object Object]","sec-ch-ua-platform":"\"Windows\"","Sec-Fetch-Site":"same-origin","Sec-Fetch-Mode":"cors","Sec-Fetch-Dest":"empty","Accept-Encoding":"gzip, deflate, br","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"}
    pre_data=requests.get(secret_upload_pre_url+"?fileExt="+ext,headers=headers, verify=False).json()
    try:
        token=pre_data["uploadToken"]["token"]
    except KeyError:
        return None
    finally:
        pre_data_2=pre_data["uploadToken"]
    multipart_encoder = encoder.MultipartEncoder(
        fields={
            'appKey': pre_data_2["appKey"],
            'expires': str(pre_data_2["expires"]),
            "filePath":pre_data_2["filePath"],
            "token":token,
            'file': (fileName, open(filePath,"rb"), '')
        })
    


    headers={"sec-ch-ua":"\"Microsoft Edge\";v=\"105\", \" Not;A Brand\";v=\"99\", \"Chromium\";v=\"105\"","Accept":"application/json, text/plain, */*","sec-ch-ua-mobile":"?0","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27","sec-ch-ua-platform":"\"Windows\"","Host":"cystorage.cycore.cn","Sec-Fetch-Site":"cross-site","Sec-Fetch-Mode":"cors","Sec-Fetch-Dest":"empty","Accept-Encoding":"gzip, deflate, br","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"}
    headers['Content-Type'] = multipart_encoder.content_type
    r = requests.post(secret_upload_url, data=multipart_encoder,headers=headers,verify=False).json()
    try:
        res=(r["url"])
    except KeyError:
        sys.exit(1)
        res="" 
    return res

def uploadAllFilesAndGetMarkDown(fileList):
    data={}
    for i in fileList:
        data[i]=uploadFile(i)
    #write markdown
    res=""
    for i in data:
        res+=(f"[点击下载{i}](https://j.keygen.eu.org/#{data[i]})\n")
    return res
def getLatestRelease():
    headers={"Authorization":"token "+github_token}
    r=requests.get("https://api.github.com/repos/Alexander-Porter/idv-login/releases/latest",headers=headers)
    return r.json()

def downloadToPath(url, path):
    r=requests.get(url)
    with open(path, "wb") as f:
        f.write(r.content)
    return path

def upload_asset(file_path, release_id):
    #https://gitee.com/api/v5/repos/{owner}/{repo}/releases/{release_id}/attach_files
    url=f"https://gitee.com/api/v5/repos/{os.getenv('GITEE_ROPE')}/releases/{release_id}/attach_files"
    mulitpart_encoder = encoder.MultipartEncoder(
        fields={
            'access_token': os.getenv('GITEE_TOKEN'),
            'file': (os.path.split(file_path)[1], open(file_path, 'rb'), 'application/octet-stream')
        }
    )
    headers = {
        "content-type": mulitpart_encoder.content_type
    }
    r = requests.post(url, data=mulitpart_encoder, headers=headers)
    return r.json()


def releaseToGitee(releaseData,fileList=[]):
    url=f"https://gitee.com/api/v5/repos/{os.getenv("GITEE_ROPE")}/releases"
    data={
        "access_token": os.getenv("GITEE_TOKEN"),
        "tag_name": releaseData["tag_name"],
        "name": releaseData["name"],
        "body": releaseData["body"],
        "target_commitish": releaseData["target_commitish"]
    }
    giteeData=requests.post(url, data=data).json()
    giteeReleaseId=str(giteeData["id"])
    for i in fileList:
        upload_asset(i, giteeReleaseId)
    
def updateCloudRes():
    #get now cloud res
    url="https://api.github.com/repos/Alexander-Porter/idv-login/contents/assets/cloudRes.json"
    headers={"Authorization":"token "+github_token}
    r=requests.get(url,headers=headers)
    fileInfo=r.json()
    sha=fileInfo["sha"]
    import base64
    import json
    content=base64.b64decode(fileInfo["content"]).decode()
    data=json.loads(content)
    #update cloud res
    releaseData=getLatestRelease()
    data["version"]=releaseData["tag_name"]
    import time
    data["lastModified"]=int(time.time())
    data["downloadUrl"]=f"https://gitee.com/{os.getenv('GITEE_ROPE')}/releases/tag/{releaseData['tag_name']}"
    data["detail"]=releaseData["body"]
    commitMessage=f"Update cloudRes.json to {releaseData['tag_name']}"
    dataStr=json.dumps(data)
    dataStr=base64.b64encode(dataStr.encode()).decode()
    data={
        "message":commitMessage,
        "content":dataStr,
        "sha":sha
    }
    r=requests.put(url,headers=headers,json=data)
    print(r.json())

if __name__=='__main__':
    requests.packages.urllib3.disable_warnings()
    os.mkdir(sys.argv[1])
    releaseData=getLatestRelease()
    for i in releaseData["assets"]:
        downloadToPath(i["browser_download_url"],os.path.join(sys.argv[1],i["name"]))
    targetDir=sys.argv[1]
    fileList=[]
    for root, dirs, files in os.walk(targetDir):
        for file in files:
            fileList.append(os.path.join(root, file))
    try:
        releaseData["body"]+=('### 备用下载地址\n'+uploadAllFilesAndGetMarkDown(fileList))
        print(json.dumps(releaseData))
        releaseToGitee(releaseData,fileList)
    except:
        traceback.print_exc()
        traceback.print_stack()
    updateCloudRes()
