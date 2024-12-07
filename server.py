import socket
import os
from pathlib import Path
import json
import ffmpeg

class TCPServer:
    def __init__(self, server_address, server_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = server_address
        self.server_port = server_port
        self.chunk_size = 1400

        self.dpath = 'processed'
        if not os.path.exists(self.dpath):
            os.makedirs(self.dpath)
        
        print('Starting up on {}'.format(server_address, server_port))

        # 前の接続が残っていた場合接続解除
        try:
            os.unlink(server_address)
        except FileNotFoundError:
            pass
        self.sock.bind((server_address, server_port))
        self.sock.listen()
    
    def handle_message(self):
        while True:
            connection, client_address = self.sock.accept()
            try:
                print('connection from', client_address)

                header = connection.recv(8)
                json_length = int.from_bytes(header[0:2], "big")
                media_type_length = int.from_bytes(header[2:3], "big")
                file_size = int.from_bytes(header[3:8], "big")

                if file_size == 0:
                    raise Exception('No data to read from client.')

                body = connection.recv(json_length + media_type_length)
                json_file = json.loads(body[:json_length].decode("utf-8"))
                media_type = body[json_length:].decode("utf-8")

                file_name = json_file['file_name']
                input_file_path = os.path.join(self.dpath, file_name)

                try:
                    with open(input_file_path,'wb+') as f:
                        # すべてのデータの読み書きが終了するまで、クライアントから読み込まれます
                        while file_size > 0:
                            data = connection.recv(file_size if file_size <= self.chunk_size else self.chunk_size)
                            f.write(data)
                            print('recieved {} bytes'.format(len(data)))
                            file_size -= len(data)
                            print(file_size)
                    
                    response_state = bytes([0x00]) # 成功
                    connection.send(response_state)
                
                except Exception as e:
                    print('Error: ' + str(e))
                    response_state = bytes([0x01]) # エラー
                    connection.send(response_state)

                    print("Closing current connection")
                    connection.close()

                print('Finished downloading the file from client.')

                output_file_path = self.process(json_file, input_file_path, file_name)

                self.send_file(connection, output_file_path)
            
            
            except Exception as e:
                print('Error: ' + str(e))

                media_type_bytes_length = 0
                file_size = 0

                json_file = {
                    'error': True,
                    'error_message': str(e)
                }

                json_string_bytes = json.dumps(json_file).encode('utf-8')
                json_string_bytes_length = len(json_string_bytes)

                header = self.protocol_header(json_string_bytes_length, media_type_bytes_length, file_size)
                connection.sendall(header)
                body = json_string_bytes
                connection.sendall(body)


            finally:
                print("Closing current connection")
                connection.close()
    
        
    def process(self, json_file, input_file_path, file_name):
        operation = json_file['operation']

        if operation == 1:
            return self.compress_video(input_file_path, file_name)

        elif operation == 2:
            resolution = json_file['resolution']
            return self.change_resolution(input_file_path, file_name, resolution)

        elif operation == 3:
            aspect_ratio = json_file['aspect_ratio']
            return self.change_aspect_ratio(input_file_path, file_name, aspect_ratio)
        
        elif operation == 4:
            return self.convert_to_audio(input_file_path, file_name)
        
        elif operation == 5:
            start_time = json_file['start_time']
            duration = json_file['duration']
            return self.create_gif(input_file_path, file_name, start_time, duration)
    
    
    def compress_video(self, input_file_path, file_name, bitrate='1M'):
        output_file_path = os.path.join(self.dpath, 'compressed_'+file_name)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        ffmpeg.input(input_file_path).output(output_file_path, b=bitrate).run()
        os.remove(input_file_path)
        return output_file_path
    
    def change_resolution(self, input_file_path, file_name, resolution):
        output_file_path = os.path.join(self.dpath, 'changed_resolution_'+file_name)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        ffmpeg.input(input_file_path).output(output_file_path, vf=f"scale={resolution}").run()
        os.remove(input_file_path)
        return output_file_path

    def change_aspect_ratio(self, input_file_path, file_name, aspect_ratio):
        output_file_path = os.path.join(self.dpath, 'changed_aspect_ratio_'+file_name)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        ffmpeg.input(input_file_path).output(output_file_path, vf=f"setdar={aspect_ratio}").run()
        os.remove(input_file_path)
        return output_file_path
    
    def convert_to_audio(self, input_file_path, file_name):
        output_file_path = os.path.join(self.dpath, 'converted_to_audio_' + os.path.splitext(file_name)[0] + '.mp3')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        ffmpeg.input(input_file_path).output(output_file_path, acodec='mp3').run()
        os.remove(input_file_path)
        return output_file_path
    
    def create_gif(self, input_file_path, file_name, start_time, duration, fps=10):
        output_file_path = os.path.join(self.dpath, 'created_gif_' + os.path.splitext(file_name)[0] + '.gif')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        ffmpeg.input(input_file_path, ss=start_time, t=duration).output(output_file_path, vf=f"fps={fps}", pix_fmt='rgb24').run()
        os.remove(input_file_path)
        return output_file_path
    

    def send_file(self, connection, output_file_path):
        _, media_type = os.path.splitext(output_file_path)
        media_type_bytes = media_type.encode('utf-8')
        media_type_bytes_length = len(media_type_bytes)
        
        with open(output_file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            f.seek(0,0)

            file_name = os.path.basename(f.name)

            json_file = {
                'file_name': file_name,
                'error': False,
                'error_message': None
            }

            json_string_bytes = json.dumps(json_file).encode('utf-8')
            json_string_bytes_length = len(json_string_bytes)

            header = self.protocol_header(json_string_bytes_length, media_type_bytes_length, file_size)
            connection.sendall(header)
            body = json_string_bytes + media_type_bytes
            connection.sendall(body)

            data = f.read(self.chunk_size)
            while data:
                print("Sending...")
                connection.send(data)
                data = f.read(self.chunk_size)
    

    def protocol_header(self, json_length, media_type_length, payload_length):
        return json_length.to_bytes(2, "big") + media_type_length.to_bytes(1,"big") + payload_length.to_bytes(5,"big")

    
    def start(self):
        self.handle_message()


if __name__ == "__main__":
    server_address = '0.0.0.0'
    tcp_server_port = 9001
    tcp_server = TCPServer(server_address, tcp_server_port)
    tcp_server.start()