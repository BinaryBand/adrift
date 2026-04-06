from typing import Any

def client(service_name: str, **kwargs: Any) -> Any: ...

class session:
    class Session:
        def client(self, service_name: str, **kwargs: Any) -> Any: ...
