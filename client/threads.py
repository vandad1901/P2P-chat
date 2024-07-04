from PyQt6.QtCore import QThread, pyqtSignal
import socket
import requests
import re

connectedPattern = re.compile(b"^<(.*),connected<EOF>>$")
acceptedPattern = re.compile(b"^<(.*),accepted<EOF>>$")
msgPattern = re.compile(b"^<(.*),msg,(.*)<EOF>>$")
filePattern = re.compile(
    b"^<(.*)<SEP>filename<SEP>(.*)<SEP>data<SEP>(.*)<EOF>>$", re.DOTALL
)
closedPattern = re.compile(b"^<(.*),closed<EOF>>$")


class FetchUsernamesThread(QThread):
    usernamesFetched = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.url = "http://localhost:8111/peers"

    def run(self):
        usernames = requests.get(self.url).json()["peers"]
        self.usernamesFetched.emit(usernames)


class ConnectionHandler(QThread):
    newConnectionSignal = pyqtSignal(str)
    connectionAcceptedSignal = pyqtSignal(str)
    newMessageSignal = pyqtSignal(str, str)
    newFileSignal = pyqtSignal(str, str, bytes)
    connectionClosedSignal = pyqtSignal(str)

    def __init__(self, sock: socket.socket):
        super().__init__()
        self.sock = sock

    def run(self):
        self.sock.listen(1)
        while True:
            conn, addr = self.sock.accept()
            with conn:
                print(f"Connected by {addr}")
                while True:
                    data = bytearray()
                    connectionAborted = False
                    while len(data) == 0 or data.endswith(b"<EOF>>") == False:
                        # print(data)
                        chunk = conn.recv(1024)
                        if not chunk:
                            connectionAborted = True
                            break  # Abort connection
                        data += chunk
                    if not data or connectionAborted:
                        break
                    print(f"Received: {data}")
                    if x := connectedPattern.match(data):
                        self.newConnectionSignal.emit(x.group(1).decode("utf-8"))
                    elif x := acceptedPattern.match(data):
                        self.connectionAcceptedSignal.emit(x.group(1).decode("utf-8"))
                    elif x := msgPattern.match(data):
                        self.newMessageSignal.emit(
                            x.group(1).decode("utf-8"), x.group(2).decode("utf-8")
                        )
                    elif x := filePattern.match(data):
                        self.newFileSignal.emit(
                            x.group(1).decode("utf-8"),
                            x.group(2).decode("utf-8"),
                            x.group(3),
                        )
                    elif x := closedPattern.match(data):
                        self.connectionClosedSignal.emit(x.group(1).decode("utf-8"))
