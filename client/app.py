import sys
from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QMainWindow,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QPlainTextEdit,
    QLabel,
    QHBoxLayout,
    QFileDialog,
)
from PyQt6.QtCore import Qt
from threads import ConnectionHandler, FetchUsernamesThread
import socket
import requests
import random
import time

myPort = random.randint(20000, 30000)
listenSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


class RegisterWindow(QMainWindow):
    def __init__(self, username: str | None = None):
        super().__init__()

        self.setWindowTitle("Register")

        self.userInput = QLineEdit()
        self.userInput.setPlaceholderText("Enter username")
        self.portInput = QLineEdit()
        self.portInput.setText(str(myPort))
        self.portInput.setPlaceholderText("Port")
        self.button = QPushButton("Submit")
        self.button.clicked.connect(self.registerUsername)

        inputsLayout = QHBoxLayout()
        inputsLayout.addWidget(self.userInput, 3)
        inputsLayout.addWidget(self.portInput, 1)
        layout = QVBoxLayout()
        layout.addLayout(inputsLayout)
        layout.addWidget(self.button)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        if username:
            self.userInput.setText(username)

    def registerUsername(self):
        username = self.userInput.text()
        port = self.portInput.text()
        print(f"Username: {username}")
        try:
            r = requests.post(
                "http://localhost:8111/register",
                json={
                    "username": username,
                    "ip": "127.0.0.1",  # replace with global ip
                    "port": port,
                },
            )
        except requests.exceptions.ConnectionError:
            errorLabel = QLabel("STUN Server is offline")
            errorLabel.setMargin(10)
            self.resize(errorLabel.sizeHint())
            self.setCentralWidget(errorLabel)
            return
        listenSock.bind(("127.0.0.1", int(port)))
        self.userSelectWindow = UserSelectWindow(username)
        s = self.statusBar()
        m = self.menuBar()
        header_height = 0
        if m and s:
            header_height = m.height() + s.height()
        self.userSelectWindow.move(self.pos().x(), self.pos().y() + header_height)
        self.userSelectWindow.show()
        self.close()


class UserSelectWindow(QMainWindow):
    def __init__(self, username: str):
        super().__init__()
        self.myUsername = username
        self.chatWindows = dict()

        self.setWindowTitle("User select screen")
        self.loadingMessage = QLabel("Loading Users...")
        self.loadingMessage.setMargin(10)
        self.resize(self.loadingMessage.sizeHint())
        self.setCentralWidget(self.loadingMessage)

        self.fetchUsernamesThread = FetchUsernamesThread()
        self.fetchUsernamesThread.usernamesFetched.connect(self.updateUsernames)
        self.fetchUsernamesThread.start()

        self.connectionHandler = ConnectionHandler(listenSock)
        self.connectionHandler.newConnectionSignal.connect(
            self.handleNewConnectionRequest
        )
        self.connectionHandler.connectionAcceptedSignal.connect(
            self.handleConnectionAccepted
        )
        self.connectionHandler.newMessageSignal.connect(self.handleNewMessage)
        self.connectionHandler.newFileSignal.connect(self.handleNewFile)
        self.connectionHandler.connectionClosedSignal.connect(
            self.handleConnectionClosed
        )
        self.connectionHandler.start()

    def updateUsernames(self, usernames):
        self.setFixedWidth(250)
        layout = QVBoxLayout()
        for username in [u for u in usernames if u != self.myUsername]:
            button = QPushButton(username)
            button.clicked.connect(
                lambda state, u=username: self.openChat(u, isRequest=False)
            )
            layout.addWidget(button)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def openChat(self, username, isRequest: bool):
        otherInfo: dict = requests.get(
            "http://localhost:8111/peer_info", params={"username": username}
        ).json()

        chatWindow = ChatWindows(
            self.myUsername,
            username,
            otherInfo["ip"],
            int(otherInfo["port"]),
            isRequest,
        )
        # show the windows on top of this one
        s = self.statusBar()
        m = self.menuBar()
        header_height = 0
        if m and s:
            header_height = m.height() + s.height()
        chatWindow.move(self.pos().x(), self.pos().y() + header_height)
        chatWindow.show()
        self.chatWindows[username] = chatWindow

    def handleNewConnectionRequest(self, username):
        self.openChat(username, isRequest=True)

    def handleNewMessage(self, username, msg):
        self.chatWindows[username].recvMessage(msg)

    def handleNewFile(self, username, fileName, fileData: bytearray):
        with open(f"{username}:{fileName}", "wb") as file:
            file.write(fileData)

        self.chatWindows[username].recvMessage(f"File received: {fileName}")

    def handleConnectionAccepted(self, username):
        self.chatWindows[username].handleAccept()

    def handleConnectionClosed(self, username):
        self.chatWindows[username].handleClosed()

    def closeEvent(self, event):
        try:
            listenSock.close()  # Close the sending socket
            print("Socket closed successfully")
        except Exception as e:
            print(f"Error closing socket: {e}")
        finally:
            event.accept()  # Proceed with the window close


class ChatWindows(QMainWindow):
    def __init__(
        self,
        myUsername: str,
        otherUsername: str,
        otherIp: str,
        otherPort: int,
        isRequest: bool,
    ):
        super().__init__()
        self.myUsername = myUsername
        self.otherUsername = otherUsername
        self.ip = otherIp
        self.port = otherPort
        self.messages = []
        self.sendSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sendSock.connect((self.ip, self.port))
        except ConnectionRefusedError:
            self.setWindowTitle("Error")
            self.loadingMessage = QLabel("Peer is offline")
            self.loadingMessage.setMargin(10)
            self.resize(self.loadingMessage.sizeHint())
            self.setCentralWidget(self.loadingMessage)
            return
        self.setWindowTitle(f"Chat with {otherUsername}")
        if isRequest:
            self.showConfirmation()
        else:
            self.sendSock.sendall(f"<{self.myUsername},connected<EOF>>".encode("utf-8"))
            self.showWaitingMessage()

    def handleAccept(self):
        self.setMinimumSize(300, 200)
        self.resize(300, 200)
        self.messageInput = QLineEdit()
        self.sendFileButton = QPushButton("Send File")
        self.sendFileButton.clicked.connect(self.sendFile)
        self.sendButton = QPushButton("Send")
        self.sendButton.clicked.connect(self.sendMessage)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)

        inputLayout = QHBoxLayout()
        inputLayout.addWidget(self.messageInput, 5)
        inputLayout.addWidget(self.sendFileButton, 1)

        layout = QVBoxLayout()
        layout.addWidget(self.chat)
        layout.addLayout(inputLayout)
        layout.addWidget(self.sendButton)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def handleClosed(self):
        self.setWindowTitle("Error")
        self.loadingMessage = QLabel("Peer has disconnected")
        self.loadingMessage.setMargin(10)
        self.setMinimumSize(0, 0)
        self.resize(self.loadingMessage.sizeHint())
        self.setCentralWidget(self.loadingMessage)

    def recvMessage(self, msg: str | None = None):
        if msg == None:
            self.messages.append(
                f"{time.strftime('%H:%M:%S')} {self.otherUsername} connected"
            )
        else:
            self.messages.append(
                f"{time.strftime('%H:%M:%S')} {self.otherUsername}: {msg}"
            )
        self.chat.setPlainText("\n".join(self.messages))

    def sendMessage(self, msg):
        msg = self.messageInput.text()
        self.sendSock.sendall(f"<{self.myUsername},msg,{msg}<EOF>>".encode("utf-8"))
        self.messages.append(f"{time.strftime('%H:%M:%S')} {self.myUsername}: {msg}")
        self.chat.setPlainText("\n".join(self.messages))
        self.messageInput.clear()

    def sendFile(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Open File")
        if not filePath:
            return
        with open(filePath, "rb") as file:
            data = file.read()
            print(f"sending with bytes length: {len(data)}")
            body = (
                f"<{self.myUsername}<SEP>filename<SEP>{filePath.split('/')[-1]}<SEP>data<SEP>".encode(
                    "utf-8"
                )
                + data
                + "<EOF>>".encode("utf-8")
            )
            self.sendSock.sendall(body)

    def showConfirmation(self):
        requestText = QLabel()
        requestText.setText(
            f'Connection requested from "{self.otherUsername}". Do you accept?'
        )
        requestText.setMargin(10)
        self.setFixedWidth(requestText.sizeHint().width() + len(self.otherUsername) * 8)
        acceptButton = QPushButton("Yes")
        rejectButton = QPushButton("No")
        acceptButton.clicked.connect(
            lambda: self.sendSock.sendall(
                f"<{self.myUsername},accepted<EOF>>".encode("utf-8")
            )
        )
        acceptButton.clicked.connect(self.handleAccept)
        rejectButton.clicked.connect(self.close)

        layout = QVBoxLayout()
        layout.addWidget(requestText)
        layout.addWidget(acceptButton)
        layout.addWidget(rejectButton)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def showWaitingMessage(self):
        self.loadingMessage = QLabel("Waiting for peer to accept...")
        self.loadingMessage.setMargin(10)
        self.resize(self.loadingMessage.sizeHint())
        self.setCentralWidget(self.loadingMessage)

    def closeEvent(self, event):
        try:
            self.sendSock.sendall(f"<{self.myUsername},closed<EOF>>".encode("utf-8"))
            self.sendSock.close()  # Close the sending socket
            print("Socket closed successfully")
        except Exception as e:
            print(f"Error closing socket: {e}")
        finally:
            event.accept()  # Proceed with the window close


app = QApplication([])

window = RegisterWindow(username=sys.argv[1] if len(sys.argv) > 1 else None)
window.show()

app.exec()
