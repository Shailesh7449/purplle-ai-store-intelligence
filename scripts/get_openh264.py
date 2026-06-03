import urllib.request
import bz2
import os

def main():
    url = "https://github.com/cisco/openh264/releases/download/v1.8.0/openh264-1.8.0-win64.dll.bz2"
    bz2_path = "openh264.bz2"
    dll_path = "openh264-1.8.0-win64.dll"
    
    print(f"Downloading OpenH264 from {url}...")
    urllib.request.urlretrieve(url, bz2_path)
    
    print("Decompressing OpenH264 DLL...")
    with bz2.open(bz2_path, "rb") as source:
        data = source.read()
        
    with open(dll_path, "wb") as dest:
        dest.write(data)
        
    # Clean up bz2 file
    if os.path.exists(bz2_path):
        os.remove(bz2_path)
        
    print("OpenH264 setup completed successfully!")

if __name__ == "__main__":
    main()
