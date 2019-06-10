def skytrack_log(function):
    """
    Decorator raise exception to skytrack
    """
    def wrapper(*args, **kwargs):
        exception = Exception("Retry decorator error.")
        try:
            return function(*args, **kwargs)
        except Exception as e:
            print('integration framework web output start')
            print(e)
            print('integration framework web output end')
            exception = e
        raise exception
    return wrapper
