import select
import socket

HOST = '127.0.0.1'
PORT = 5000

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
    server.bind((HOST, PORT))
    server.setblocking(False)
    server.listen(1)
    socks = [server]
    while True:
        try:
            readable, writable, exceptional = select.select(socks, [], [], 1)
        except KeyboardInterrupt:
            for sock in socks:
                sock.close()
            break
        for sock in readable:
            if sock is server:
                connection, addr = server.accept()
                connection.setblocking(False)
                socks.append(connection)
                print('CONNECT')
            else:
                data = sock.recv(1024)
                if data:
                    print(f'>>> {data}')
                    sock.send(data)
                else:
                    print('DISCONNECT')
                    socks.remove(sock)
