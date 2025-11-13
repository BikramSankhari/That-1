class ConnectionTimeout(Exception):
    def __init__(self, *args):
        super().__init__(*args)

class ResponseTimeOut(Exception):
    def __init__(self, *args):
        super().__init__(*args)