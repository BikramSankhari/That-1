def deco(a, b):
    def wrapper():
        def inner(*args, **kwargs):
            print(a)
            print(b)

        return inner
    return wrapper

@deco(3, 4)
def add():
    print("Added")

add()