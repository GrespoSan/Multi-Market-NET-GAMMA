"""On-demand Cboe NDX download. No unattended polling in the MVP."""
import requests

NDX_URL = 'https://cdn.cboe.com/api/global/delayed_quotes/_NDX.json'


def download_ndx(limit_mb=100) -> bytes:
    headers={'User-Agent':'Mozilla/5.0', 'Accept':'application/json',
             'Cache-Control':'no-cache'}
    with requests.get(NDX_URL, headers=headers, timeout=(8, 55), stream=True) as response:
        response.raise_for_status()
        chunks=[]
        total=0
        for chunk in response.iter_content(chunk_size=1024*1024):
            total += len(chunk)
            if total > limit_mb * 1024*1024:
                raise ValueError('Il file NDX supera la dimensione massima prevista.')
            chunks.append(chunk)
    if not chunks:
        raise ValueError('Risposta Cboe vuota')
    return b''.join(chunks)
