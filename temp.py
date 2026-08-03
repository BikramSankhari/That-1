while 0 < 1:
    try:
        1/0
    except ZeroDivisionError:
        print("division by zero")
        break

    print("This will never be printed")

print("This will be printed after the loop")