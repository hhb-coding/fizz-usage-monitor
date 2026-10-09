"""Read-only candidate/index/history audit / 只读候选文件、索引与历史审计。
Reports categories and paths only, never matched values. No Git writes or network.
仅输出风险类别与路径；不写 Git，不联网，不扫描外部运行数据。
"""
import ast
import ipaddress
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_PATHS = [
    '.env', '.env.local', '.envrc', '.ENV', 'config.json', 'config.local.toml',
    'monitor.db', 'monitor.db-wal', 'monitor.sqlite3', 'monitor.sqlite3-journal',
    'monitor.sqlite3-wal', 'monitor.SQLITE3', 'password.txt', 'PASSWORD.txt',
    'cookies.json', 'Cookie.json', 'token.json', 'Token.json', 'Session.json',
    'session.json', 'credentials.json', 'auth/state.json', 'browser_state.json',
    'browser-profile/Default/Preferences', 'profiles/state.json',
    'private/collector.py', 'data/usage.json', 'personal/account.json',
    'bills/invoice.pdf', 'billing/invoice.pdf', 'imports/usage.csv',
    'exports/usage.csv', 'logs/app.log', 'app.log', 'app.LOG',
    'backups/snapshot.zip', 'snapshot.backup', 'snapshot.sql', 'snapshot.tar.gz',
    '.venv/lib/package.py', '__pycache__/module.pyc', '.synthetic-demo',
    'screenshots/capture.png', 'capture.jpg', 'capture.pdf', 'capture.har',
]
RULES = {
    'email-shaped content': r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',
    'phone-shaped content': r'(?<!\d)(?:\+1[ .-]?)?\(\d{3}\)[ .-]?\d{3}[ .-]\d{4}(?!\d)',
    'host-specific home path': r'/(?:home|Users)/[^\s\"\'<>`]+',
    'host-specific deployment path': r'/tmp/(?:portal[^\s`\"\'<>]*|fizz-[^\s`\"\'<>]*[A-Za-z0-9]{6})',
    'credential-shaped assignment': r'(?i)(?:password|api_key|access_token|refresh_token)\s*[:=]\s*[\"\'][^\"\']+[\"\']',
    'private-key material': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'service-token-shaped content': r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b',
    'JWT-shaped content': r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b',
}


def git(*args, input=None):
    return subprocess.run(['git','-C',str(ROOT),*args],input=input,
                          text=True,capture_output=True)


def findings(text):
    result={name for name, pattern in RULES.items() if re.search(pattern,text)}
    for value in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',text):
        try:
            address=ipaddress.ip_address(value)
            if not address.is_loopback and not address.is_unspecified:
                result.add('non-loopback IP-shaped content')
        except ValueError:
            pass
    return result


def main():
    manifest=ROOT/'PUBLIC_FILES.txt'
    allowed=manifest.read_text().splitlines()
    risks=set()
    if len(allowed)!=len(set(allowed)):
        risks.add(('duplicate manifest entry','PUBLIC_FILES.txt'))
    for name in allowed:
        path=ROOT/name
        if path.is_symlink() or not path.is_file() or Path(name).is_absolute() or '..' in Path(name).parts:
            risks.add(('unsafe/missing candidate path',name))
            continue
        for category in findings(path.read_text()):
            risks.add((category,name))
    # Network/browser clients must not enter application source.
    blocked={'requests','urllib','http','socket','selenium','playwright','httpx','aiohttp'}
    for path in (ROOT/'fizz_monitor').rglob('*.py'):
        if '__pycache__' in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names=[]
            if isinstance(node,ast.Import): names=[n.name for n in node.names]
            if isinstance(node,ast.ImportFrom): names=[node.module or '']
            if any(name.split('.')[0] in blocked for name in names):
                risks.add(('network/browser import',str(path.relative_to(ROOT))))
    if git('rev-parse','--is-inside-work-tree').returncode:
        print('LIMIT: no usable Git repository; ignore/index/history checks unavailable.')
        return 1
    ignored=git('check-ignore','--no-index','--stdin',input='\n'.join(SENSITIVE_PATHS)+'\n')
    for name in set(SENSITIVE_PATHS)-set(ignored.stdout.splitlines()):
        risks.add(('sensitive category not ignored',name))
    for name in allowed:
        if git('check-ignore','--no-index',name).returncode == 0:
            risks.add(('public candidate unexpectedly ignored',name))
    untracked=git('ls-files','--others','--exclude-standard','-z')
    for name in filter(None,untracked.stdout.split('\0')):
        if name not in allowed:
            risks.add(('unlisted untracked file',name))
    tracked=git('ls-files','-z')
    for name in filter(None,tracked.stdout.split('\0')):
        if name not in allowed:
            risks.add(('unlisted indexed file',name))
            continue
        blob=git('show',':'+name)
        if blob.returncode:
            risks.add(('index content unreadable',name))
        else:
            for category in findings(blob.stdout):
                risks.add(('indexed '+category,name))
    objects=git('rev-list','--objects','--all')
    if objects.returncode:
        risks.add(('history unreadable','.git'))
    history_blobs=0
    for line in objects.stdout.splitlines():
        parts=line.split(' ',1)
        oid=parts[0]
        kind=git('cat-file','-t',oid)
        if kind.stdout.strip()!='blob':
            continue
        history_blobs+=1
        name=parts[1] if len(parts)>1 else '(unnamed history blob)'
        if name not in allowed:
            risks.add(('unlisted historical file',name))
            continue
        blob=git('cat-file','blob',oid)
        for category in findings(blob.stdout):
            risks.add(('historical '+category,name))
    if risks:
        for category,name in sorted(risks):
            print(f'REVIEW: {category}: {name}')
        print('STOP: review findings privately; no matched values are printed.')
        return 1
    print(f'PASS: {len(allowed)} public candidate contents; {len(SENSITIVE_PATHS)} exclusion probes.')
    print(f'PASS: {len(list(filter(None,tracked.stdout.split(chr(0)))))} indexed files; {history_blobs} reachable historical blobs reviewed.')
    print('PASS: no network/browser client imports in application source.')
    print('LIMIT: pattern audit is not proof of absence of every secret; human review is required.')
    return 0


if __name__=='__main__':
    sys.exit(main())
