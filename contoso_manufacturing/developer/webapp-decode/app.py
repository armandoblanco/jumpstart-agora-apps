from flask import Flask, render_template, Response, request
import os
import cv2
import json
import numpy as np
from yolov8 import YOLOv8OVMS



app = Flask(__name__)

OVMS_URL = "10.0.0.4:8080"
MODEL_NAME = ''

camera = None  # Initialized later based on the selected video

# Global variable to keep track of the latest choice of the user
latest_choice = None

def gen_frames(video_name):  
    print(video_name)

    MODEL_NAME = video_name
    print(MODEL_NAME)
    with open('config_file.json') as config_file:
        config = json.load(config_file)
    model_config = config[MODEL_NAME]

    color_palette = np.random.uniform(0, 255, size=(len(model_config['class_names']), 3))

    detector = YOLOv8OVMS(
        rtsp_url=model_config['rtsp_url'],
        class_names=model_config['class_names'],
        input_shape=model_config['input_shape'],
        color_palette=color_palette,
        confidence_thres=model_config['conf_thres'],
        iou_thres=model_config['iou_thres'],
        MODEL_NAME=MODEL_NAME, 
        OVMS_URL=OVMS_URL, 
        SAVE_IMG_LOC=False
    )
    while True:
        processed_frame = detector.run()
        ret, buffer = cv2.imencode('.jpg', processed_frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    video_name = request.args.get('video')
    if video_name is None:
        return Response('Video name parameter is missing', status=400)

    return Response(gen_frames(video_name), mimetype='multipart/x-mixed-replace; boundary=frame')  # stream the video frames

@app.route('/')
def index():
    # Get the paths to to the SVG files and the load the content
    contoso_path = os.path.join(app.root_path, 'static/images', 'contoso.svg')
    with open(contoso_path, 'r') as f:
        contoso = f.read()

    site_enterprise_path = os.path.join(app.root_path, 'static/images', 'site_enterprise.svg')
    with open(site_enterprise_path, 'r') as f:
        site_enterprise = f.read()

    site_path = os.path.join(app.root_path, 'static/images', 'site.svg') 
    with open(site_path, 'r') as f:
        site = f.read()

    enterprise_path = os.path.join(app.root_path, 'static/images', 'enterprise.svg')
    with open(enterprise_path, 'r') as f:
        enterprise = f.read()

    return render_template('index.html', contoso=contoso, site_enterprise=site_enterprise, site=site, enterprise=enterprise)

if __name__ == '__main__':
    app.run(debug=True, port=5001)

# Release the video capture object and close all windows
camera.release()
cv2.destroyAllWindows()
