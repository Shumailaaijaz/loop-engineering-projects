"""Small example module so the morning-brief script has real TODOs to find."""


def greet(name):
    # TODO: validate that name is non-empty before greeting
    # TODO: reject names longer than 100 characters
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("world"))
