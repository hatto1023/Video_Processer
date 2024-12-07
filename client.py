import socket
import sys
import os
import json
import ffmpeg
import re

class TCPClient:
    def __init__(self, server_address, server_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = server_address
        self.server_port = server_port
        self.chunk_size = 1400

        self.dpath = 'recieve'
        if not os.path.exists(self.dpath):
            os.makedirs(self.dpath)
    
    def upload_file(self):
        try:
            file_path = self.input_file_path()
            _, media_type = os.path.splitext(file_path)
            media_type_bytes = media_type.encode('utf-8')
            media_type_bytes_length = len(media_type_bytes)
            
            with open(file_path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                f.seek(0,0)

                file_name = os.path.basename(f.name)

                operation = self.input_operation()

                json_file = {
                    'file_name': file_name,
                    'operation': operation       
                }

                json_file = self.input_operation_details(operation, json_file, file_path)
                json_string_bytes = json.dumps(json_file).encode('utf-8')
                json_string_bytes_length = len(json_string_bytes)

                header = self.protocol_header(json_string_bytes_length, media_type_bytes_length, file_size)
                self.sock.sendall(header)
                body = json_string_bytes + media_type_bytes
                self.sock.sendall(body)

                data = f.read(self.chunk_size)
                while data:
                    print("Sending...")
                    self.sock.send(data)
                    data = f.read(self.chunk_size)
                
                response_bytes = self.sock.recv(16)
                response = int.from_bytes(response_bytes, "big")

                if response == 0x00:
                    print("アップロードに成功しました")
                elif response == 0x01:
                    print("アップロードに失敗しました")
                    sys.exit(1)
                else:
                    print("エラーが発生しました")
                    sys.exit(1)
                
            self.recieve_file()

        except Exception as e:
            print(f"エラーが発生しました: {e}")

        finally:
            print('closing socket')
            self.sock.close()


    def input_file_path(self):
        valid_extensions = ('.mp4', '.avi')
        while True:
            file_path = input("ファイルパスを入力してください（mp4、aviのいずれかの拡張子）: ")

            if file_path.endswith(valid_extensions):
                print(f"有効なファイルパスが入力されました: {file_path}")
                return file_path
            else:
                print("無効なファイル拡張子です。もう一度試してください。")


    # オペレーション入力    
    def input_operation(self):
        while True:
            print("1: 動画の圧縮, 2: 動画の解像度の変更, 3: 動画のアスペクト比の変更, 4: 動画を音声に変換, 5: 指定した時間範囲でGIFの作成")
            try:
                operation = int(input("オペレーションを入力してください(1-5): "))
                if operation in range(1, 6):
                    print(f"選択されたオペレーション: {operation}")
                    return operation
                else:
                    print("無効な選択です。1から5の数字を入力してください。")
            except ValueError:
                print("無効な入力です。数字を入力してください。")
    
    
    def input_operation_details(self, operation, json_file, file_path):
        if operation == 2:
            # 解像度変更の詳細を入力
            resolutions = {
                "1": "1920:1080",  # フルHD
                "2": "1280:720",   # HD
                "3": "720:480"    # SD
            }
            while True:
                print("1: フルHD(1920:1080), 2: HD(1280:720), 3: SD(720:480)")
                resolution = input("希望する解像度の番号を入力してください。: ")
                if resolution in resolutions:
                    json_file['resolution'] = resolutions[resolution]
                    break
                else:
                    print("無効な選択です。もう一度入力してください。")
        elif operation == 3:
            # アスペクト比変更の詳細を入力
            aspect_ratios = {
                "1": "16/9",
                "2": "4/3",
                "3": "1/1"
            }
            while True:
                print("1: (16:9), 2: (4:3), 3: (1:1)")
                aspect_ratio = input("希望するアスペクト比の番号を入力してください。: ")
                if aspect_ratio in aspect_ratios:
                    json_file['aspect_ratio'] = aspect_ratios[aspect_ratio]
                    break
                else:
                    print("無効な選択です。もう一度入力してください。")
        elif operation == 5:
            # GIF作成の詳細を入力
            video_duration = self.get_video_duration(file_path)
            HH = video_duration // 3600
            MM = (video_duration % 3600) // 60
            SS = video_duration % 60
            while True:
                print(f"動画の長さは{int(HH):02}:{int(MM):02}:{int(SS):02}です。")
                start_time = input("開始時間を入力してください（例: 00:00:10）: ")
                if re.match(r'^\d{2}:\d{2}:\d{2}$', start_time):
                    st_HH, st_MM, st_SS = map(int, start_time.split(":"))
                    start_time = st_HH*3600 + st_MM*60 + st_SS
                    if start_time < video_duration:
                        json_file['start_time'] = start_time
                        break
                    else:
                        print(f"動画の長さ{int(HH):02}:{int(MM):02}:{int(SS):02}未満にしてください。")
                else:
                    print("無効な時間形式です。もう一度入力してください。")
            
            while True:
                duration = input("再生時間を秒単位で入力してください（例: 10）: ")
                if duration.isdigit():
                    duration = float(duration)
                    if 0 < duration and json_file['start_time'] + duration <= video_duration:
                        json_file['duration'] = duration
                        break
                    else:
                        print(f"無効な再生時間です。再生可能時間は開始時間{start_time}から{float(video_duration-json_file['start_time'])}秒までです。もう一度入力してください。")
                else:
                    print(f"無効な再生時間です。数字を入力してください。")
        return json_file
    

    def get_video_duration(self, file_path):
        probe = ffmpeg.probe(file_path)
        video_duration = float(probe['format']['duration'])
        return video_duration
    

    def protocol_header(self, json_length, media_type_length, payload_length):
        return json_length.to_bytes(2, "big") + media_type_length.to_bytes(1,"big") + payload_length.to_bytes(5,"big")
    
    
    def recieve_file(self):
        header = self.sock.recv(8)
        json_length = int.from_bytes(header[0:2], "big")
        media_type_length = int.from_bytes(header[2:3], "big")
        file_size = int.from_bytes(header[3:8], "big")

        body = self.sock.recv(json_length + media_type_length)
        json_file = json.loads(body[:json_length].decode("utf-8"))
        media_type = body[json_length:].decode("utf-8")

        if json_file['error'] == True:
            print("エラーが発生しました")
            print(json_file['error_message'])
            sys.exit(1)

        file_name = json_file['file_name']
        output_file_path = os.path.join(self.dpath, file_name)
        print(output_file_path)

        try:
            with open(output_file_path,'wb+') as f:
                while file_size > 0:
                    data = self.sock.recv(file_size if file_size <= self.chunk_size else self.chunk_size)
                    f.write(data)
                    print('recieved {} bytes'.format(len(data)))
                    file_size -= len(data)
                    print(file_size)
            print("ダウンロードに成功しました")

        except Exception as e:
            print('Error: ' + str(e))
            print("ダウンロードに失敗しました")

    def start(self):
        try:
            self.sock.connect((self.server_address, self.server_port))
        except socket.error as err:
            print(err)
            sys.exit(1)
        self.upload_file()
        

if __name__ == "__main__":
    server_address = '0.0.0.0'
    tcp_server_port = 9001
    tcp_client = TCPClient(server_address, tcp_server_port)
    tcp_client.start()