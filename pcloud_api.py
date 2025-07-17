import aiohttp

class PyCloudAsync:
    """Simple async wrapper for PCloud API."""
    endpoints = {
        "api": "https://api.pcloud.com/",
        "eapi": "https://eapi.pcloud.com/",
    }

    def __init__(self, token, endpoint="api"):
        self.token = token
        if endpoint not in self.endpoints:
            raise ValueError("Endpoint (%s) not found. Use one of: %s", endpoint, ",".join(self.endpoints.keys()),)
        else:
            self.endpoint = self.endpoints.get(endpoint)
        self.session = None
    
    async def connect(self):
        """Creates a session, must be called before any requests."""
        self.session = aiohttp.ClientSession(base_url=self.endpoint, timeout=aiohttp.ClientTimeout(10))

    async def disconnect(self):
        if not self.session: return
        await self.session.close()
        self.session = None

    def change_token(self, token):
        self.token = token
    
    async def _do_request(self, method, url, auth=True, data = None, params: dict={}, **kwargs) -> dict:
        if not self.token: raise Exception("PCloud token is missing.")
        if not self.session: raise Exception("Not connected to PCloud API, call connect() first.")
        params.update(kwargs)
        if auth: params['auth'] = self.token
        async with self.session.request(method, url, data=data, params=params) as response:
            response_json = await response.json()
            if response_json["result"] != 0:
                raise Exception(f"Failed to {method} {url}: code: {response_json['result']}, error: {response_json.get('error', 'Unknown error')}")
            return response_json
        
    async def getdigest(self):
        resp = await self._do_request("GET", "getdigest", False)
        return bytes(resp["digest"], "utf-8")
        
    async def get_pcloud_token(self, email, password, verbose=False):
        """Logs into pCloud and returns the token."""
        response = await self._do_request("POST", 'userinfo', False, params={'getauth': 1, 'username': email, 'password': password})
        token = response['auth']
        if verbose: print(token)
        return token
    
    async def userinfo(self):
        return await self._do_request("GET", "userinfo")

    async def listfolder(self, folder: str):
        return await self._do_request("GET", "listfolder", params={'path': f'/{folder}'})
    
    async def getfilelink(self, fileid: int) -> str:
        file_url = await self._do_request("GET", "getfilelink", params={'fileid': fileid})
        download_url = file_url['hosts'][0] + file_url['path']
        return download_url
    
    async def get_all_links(self, fileid: int):
        return await self._do_request("GET", "getfilelink", params={'fileid': fileid})

    async def get_file(self, file: str, folder: str):
        files = await self.listfolder(folder)
        file_info = next((f for f in files.get('metadata', {}).get('contents', []) if f['name'] == file), None)
        if not file_info: return None
        download_url = await self.getfilelink(file_info['fileid'])
        return download_url
    
    async def uploadfile(self, file: str, content: str, folder: str):
        data = aiohttp.FormData()
        data.add_field('filename', content, filename=file)
        await self._do_request("POST", "uploadfile", data=data, params={'path': f'/{folder}'})

    async def search(self, query: str, **kwargs):
        return await self._do_request("GET", 'search', params={'query': query, **kwargs})
    
    async def stat(self, **kwargs):
        return await self._do_request("GET", "stat", **kwargs)
    
    async def invite(self, **kwargs):
        return await self._do_request("GET", "invite", **kwargs)

    async def userinvites(self, **kwargs):
        return await self._do_request("GET", "userinvites", **kwargs)

    async def logout(self, **kwargs):
        return await self._do_request("GET", "logout", **kwargs)

    async def listtokens(self, **kwargs):
        return await self._do_request("GET", "listtokens", **kwargs)

    async def deletetoken(self, **kwargs):
        return await self._do_request("GET", "deletetoken", **kwargs)
