import zipfile, os

src = r'C:\Users\Yogi\.minimax-agent\projects\JarvisPro_upgraded'
out = r'C:\Users\Yogi\.minimax-agent\projects\JarvisPro_upgraded\JarvisPro_Final_v1.0.zip'
exclude_dirs = {'__pycache__', '.git', '.github', 'node_modules', '.venv', 'venv', 'dist', 'build', '.idea', '.pytest_cache', '__pypackages__'}
exclude_files = {'.pyc', '.log', '.tmp', '.cache', '.pyo', '.pyd', '.so', '.dll'}

with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if any(file.endswith(ext) for ext in exclude_files):
                continue
            fp = os.path.join(root, file)
            arcname = os.path.relpath(fp, src).replace(os.sep, '/')
            zf.write(fp, arcname)

size = os.path.getsize(out)
count = len(zf.namelist()) if 'zf' in dir() else 0
print(f'Created: {out}')
print(f'Files: {count}, Size: {size/1024/1024:.1f} MB')
