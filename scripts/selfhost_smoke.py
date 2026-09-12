#!/usr/bin/env python3
"""Real inference acceptance check. Use a dedicated account; it creates a conversation."""
import argparse
import getpass
import json
import time
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('audio', type=Path)
parser.add_argument('--server', default='http://127.0.0.1:8080')
parser.add_argument('--email', required=True)
parser.add_argument('--query', default='conversation')
args = parser.parse_args()
password = getpass.getpass('Local account password: ')
with httpx.Client(base_url=args.server.rstrip('/'), timeout=300, trust_env=False, follow_redirects=False) as client:
    response = client.post('/v1/auth/login', json={'email': args.email, 'password': password})
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
    with args.audio.open('rb') as audio:
        response = client.post('/v1/import/audio', files={'file': (args.audio.name, audio)})
    response.raise_for_status()
    job = response.json()['job_id']
    print('Durably accepted:', job, flush=True)
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        response = client.get('/v1/import/jobs/' + job)
        response.raise_for_status()
        status = response.json()
        if status['status'] in {'failed', 'completed', 'cancelled'}:
            break
        time.sleep(3)
    else:
        raise SystemExit('Timed out waiting. The durable job and original remain available.')
    if status['status'] != 'completed':
        raise SystemExit('Processing did not complete: ' + status['status'])
    cid = status['result']['conversation_id']
    conversation = client.get('/v1/conversations/' + cid).json()
    assert conversation['transcript_segments'], 'No voice detected in input'
    assert conversation['structured']['overview'], 'Summary missing'
    for _ in range(120):
        result = client.get('/v1/search', params={'q': args.query}).json()
        if result.get('results'):
            break
        time.sleep(3)
    assert result.get('results'), 'Search indexing not complete'
    urls = client.get(f'/v1/sync/audio/{cid}/urls').json()
    if conversation.get('audio_files'):
        playback = httpx.get(urls['audio_files'][0]['signed_url'], timeout=30, trust_env=False)
        playback.raise_for_status()
        assert playback.content
    reply = client.post('/v2/messages', json={'text': 'Resume esta conversación.', 'context': {'conversation_id': cid}})
    reply.raise_for_status()
    assert 'done: ' in reply.text and 'error: ' not in reply.text, 'Chat stream did not complete'
    print(json.dumps({'conversation_id': cid, 'transcription': 'passed', 'summary': 'passed', 'search': 'passed', 'chat': 'passed'}))
