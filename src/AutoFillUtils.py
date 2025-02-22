import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from envmgr import genv

class AutoFillRecord:
    def __init__(self, username=None, password=None, record_dict=None):
        if record_dict:
            self.hashed_username = record_dict["hashed_username"]
            self.truncated_username = record_dict["truncated_username"]
            self.encrypted_password = base64.b64decode(record_dict["encrypted_password"])
            self.iv = base64.b64decode(record_dict["iv"])
        elif username and password:
            self.original_username = username
            self.hashed_username = self.hash_username(username)
            self.truncated_username = self.truncate_username(username)
            self.iv = get_random_bytes(16)  # AES block size is 16 bytes
            self.encrypted_password = self.encrypt_password(username, password)
        else:
            raise ValueError("Either username and password or record_dict must be provided")

    def hash_username(self, username):
        return hashlib.sha256(username.encode()).hexdigest()

    def truncate_username(self, username):
        if len(username) <= 4:
            return username[0] + '*'*(len(username)-1)
        return username[:2] + '*' * (len(username) - 4) + username[-2:]

    def encrypt_password(self, username, password):
        key = hashlib.sha256(username.encode()).digest()  # AES key must be either 16, 24, or 32 bytes long
        cipher = AES.new(key, AES.MODE_CBC, self.iv)
        encrypted_password = cipher.encrypt(pad(password.encode(), AES.block_size))
        return encrypted_password

    def decrypt_password(self, username, encrypted_password):
        key = hashlib.sha256(username.encode()).digest()
        cipher = AES.new(key, AES.MODE_CBC, self.iv)
        decrypted_password = unpad(cipher.decrypt(encrypted_password), AES.block_size)
        return decrypted_password.decode()

    def to_dict(self):
        return {
            "hashed_username": self.hashed_username,
            "truncated_username": self.truncated_username,
            "encrypted_password": base64.b64encode(self.encrypted_password).decode('utf-8'),
            "iv": base64.b64encode(self.iv).decode('utf-8')
        }
    

class RecordMgr:
    def __init__(self):
        self.records = [AutoFillRecord(record_dict=i) for i in genv.get("autoFillData",[])]

    def add_record(self, username, password)->AutoFillRecord:
        record = AutoFillRecord(username=username, password=password)
        hashed_username = hashlib.sha256(username.encode()).hexdigest()
        for i in self.records:
            if i.hashed_username == hashed_username:
                self.records.remove(i)
        self.records.append(record)
        genv.set("autoFillData",[i.to_dict() for i in self.records],True)
        return record

    def find_password(self, username):
        hashed_username = hashlib.sha256(username.encode()).hexdigest()
        for record in self.records:
            if record.hashed_username == hashed_username:
                return record.decrypt_password(username, record.encrypted_password)
        return None
    
    def list_records(self):
        return [i.truncated_username for i in self.records]
    
    def remove_record(self, username):
        hashed_username = hashlib.sha256(username.encode()).hexdigest()
        for i in self.records:
            if i.hashed_username == hashed_username or i.truncated_username == username:
                self.records.remove(i)
                genv.set("autoFillData",[i.to_dict() for i in self.records],True)

    def clear_records(self):
        self.records = []
        genv.set("autoFillData",[],True)

    def untruncate_username(self, username):
        hashed_username = hashlib.sha256(username.encode()).hexdigest()
        for i in self.records:
            if i.hashed_username == hashed_username:
                i.truncated_username= username
                genv.set("autoFillData",[i.to_dict() for i in self.records],True)
    
    def add_untruncate_record(self, username, password):
        record = self.add_record(username, password)
        self.untruncate_username(username)
        return record

if __name__ == "__main__":
    mgr = RecordMgr()
    print(mgr.list_records())  # 输出: []