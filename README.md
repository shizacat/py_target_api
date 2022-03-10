# Description

Python library for API of myTarget.

He was take from: https://github.com/wreckah/target_api.

## Using

### Initializing API client

```python
import target_api_client

client_id = 'Yu1ES2t2VuPBYQ2f'
client_secret = '8rhRaKLEnv*****IdqmkaiQkqO8HUYL2TObVB'

def print_token(token):
    print("Token:", token)

client = target_api_client.TargetApiClient(
    client_id, client_secret, is_sandbox=True)
client.get_token()  # Obtaining an access token
```

# Links

- Docs: https://target.my.com/doc/api/ru/info/ApiAuthorization
