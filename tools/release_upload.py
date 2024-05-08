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
        res+=(f"![{i}]({data[i]})\n")
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
def releaseToGitee(releaseData):
    url=f"https://gitee.com/api/v5/repos/{os.getenv("GITEE_ROPE")}/releases"
    data={
        "access_token": os.getenv("GITEE_TOKEN"),
        "tag_name": releaseData["tag_name"],
        "name": releaseData["name"],
        "body": releaseData["body"],
        "target_commitish": releaseData["target_commitish"]
    }
    return requests.post(url, data=data).text

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
        releaseData["body"]+=uploadAllFilesAndGetMarkDown(fileList)
        print(json.dumps(releaseData))
        releaseToGitee(releaseData)
    except:
        traceback.print_exc()
        traceback.print_stack()
        sys.exit(1)
