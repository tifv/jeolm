from functools import wraps

# pylint: disable=protected-access

def _cache_node(key_function):
    """Decorator factory for NodeFactory classes methods."""
    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            key = key_function(self, *args, **kwargs)
            try:
                return self._nodes[key]
            except KeyError:
                pass
            node = self._nodes[key] = method(self, *args, **kwargs)
            return node
        return wrapper
    return decorator

# pylint: enable=protected-access

