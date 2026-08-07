import os
import urllib.request
import zipfile

url = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-bin-x64.zip"
zip_path = "whisper-bin-x64.zip"
extract_dir = "bin"

print(f"Downloading {url}...")
urllib.request.urlretrieve(url, zip_path)
print("Downloaded. Extracting...")

os.makedirs(extract_dir, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_dir)

print("Extracted. Contents:")
for root, dirs, files in os.walk(extract_dir):
    for file in files:
        print(os.path.join(root, file))

# Clean up zip file
os.remove(zip_path)
print("Done!")
