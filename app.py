from flask import Flask, request, render_template, jsonify, redirect
import pandas as pd
import os
import requests
from PIL import Image
import time
from pathlib import Path
from threading import Thread
import logging

app = Flask(__name__)

# Configure upload folder based on environment
if os.environ.get('RENDER'):
    # On Render, use the persistent storage directory
    UPLOAD_FOLDER = '/opt/render/project/src/uploads/'
else:
    # Locally, use the uploads directory in the current folder
    UPLOAD_FOLDER = 'uploads/'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Global variable to track progress
progress_data = {
    'progress': 0,
    'total_images': 0,
    'message': ''
}

logging.basicConfig(level=logging.DEBUG)

def get_download_folder():
    """Get the download folder path based on environment."""
    if os.environ.get('RENDER'):
        # On Render, use a subdirectory in the persistent storage
        return '/opt/render/project/src/downloads'
    else:
        # Locally, use the user's Downloads folder
        return str(Path.home() / "Downloads")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global progress_data
    progress_data['progress'] = 0  # Reset progress
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file:
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        wers_codes_input = request.form.get('wers_codes')
        wers_column = request.form.get('wers_column')
        image_column = request.form.get('image_column')

        if wers_codes_input:
            wers_codes_list = [code.strip() for code in wers_codes_input.replace(',', '\n').split('\n') if code.strip()]
        else:
            wers_codes_list = None

        download_folder = os.path.join(get_download_folder(), os.path.splitext(filename)[0])
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)

        # Start image download in a separate thread
        Thread(target=download_images, args=(filepath, wers_column, image_column, wers_codes_list, download_folder)).start()
        
        return render_template('index.html', success="Processing images. Check progress.", time_taken=None)

@app.route('/progress', methods=['GET'])
def progress():
    """Endpoint to get the current progress."""
    return jsonify(progress_data)

def download_images(filepath, wers_column, image_column, wers_codes_list, download_folder):
    global progress_data
    logging.info("Starting download_images function.")
    df = pd.read_excel(filepath)
    df = df.dropna(subset=[wers_column, image_column])  # Drop rows with NaN values in the specified columns
    df[wers_column] = df[wers_column].astype(str)
    df[image_column] = df[image_column].astype(str)

    if wers_codes_list:
        df = df[df[wers_column].isin(wers_codes_list)]

    processed = set()
    base_url = 'https://shop.ford.com/'
    total_images = df.shape[0]
    progress_data['total_images'] = total_images

    start_time = time.time()  # Track the start time

    for index, row in df.iterrows():
        wers_code = row[wers_column]
        image_link = row[image_column]
        if (wers_code, image_link) in processed:
            continue
        processed.add((wers_code, image_link))

        full_url = base_url + image_link
        logging.info(f"Attempting to download image from: {full_url}")
        try:
            response = requests.get(full_url, verify=False)  # Disable SSL verification
            if response.status_code == 200:
                image_path = os.path.join(download_folder, f"{wers_code}.png")
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Downloaded image and saved to: {image_path}")
                convert_to_jpg(image_path, wers_code, download_folder)
            else:
                logging.error(f"Failed to download image, status code: {response.status_code}")
        except Exception as e:
            logging.error(f"Error downloading image: {e}")

        # Update progress
        progress_data['progress'] = (index + 1) / total_images * 100

    end_time = time.time()  # Track the end time
    elapsed_time = round(end_time - start_time, 2)  # Calculate elapsed time
    return_progress_message(elapsed_time)

def return_progress_message(elapsed_time):
    """Return a success message with the time taken."""
    global progress_data
    progress_data['progress'] = 100  # Complete the progress
    progress_data['message'] = f"Successfully completed! Time taken: {elapsed_time} seconds."

def convert_to_jpg(png_path, wers_code, download_folder):
    img = Image.open(png_path)
    jpg_path = os.path.join(download_folder, f"{wers_code}.jpg")
    rgb_img = img.convert('RGB')
    rgb_img.save(jpg_path)
    os.remove(png_path)  # Remove the original PNG file

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
