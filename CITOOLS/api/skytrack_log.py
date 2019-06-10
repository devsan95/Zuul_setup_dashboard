def skytrack_log(function):
    """
    Decorator raise exception to skytrack
    """
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as e:
            print('integration framework web output start')
            print(e)
            print('integration framework web output end')
            exception = e
            raise exception
    return wrapper


def skytrack_output(messages):
    print('[SKYTRACK] integration framework web output start')
    if isinstance(messages, list):
        for message in messages:
            print message
    else:
        print messages
    print('[SKYTRACK] integration framework web output end')
