# Optical Business Solutions (Self Checkout and Inventory Management System using YOLO26)
<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Ultralytics](https://img.shields.io/badge/Ultralytics%20YOLO26-111F68?style=for-the-badge&logo=ultralytics&logoColor=white)](https://www.ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
[![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

A computer vision powered self-checkout billing and inventory management system that detects products in real time, automates customer billing, and keeps inventory in sync. Built with YOLO26, FastAPI, and Tailwind CSS.

<!-- TABLE OF CONTENTS -->
<details>
<summary> Table of Contents</summary>
  <ol>
    <li><a href="#core-features">Core Features</a></li>
    <li><a href="#screenshots--demo">Screenshots & Demo</a></li>
    <li><a href="#tech-stack">Tech Stack</a></li>
    <li><a href="#dataset">Dataset</a></li>
    <li><a href="#installation--setup">Installation & Setup</a></li>
    <li><a href="#project-structure">Project Structure</a></li>
    <li><a href="#acknowledgements">Acknowledgements</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>

<a id="core-features"></a>
## 🎯 Core Features

- **CV Powered Billing**: Real-time object detection and tracking using YOLO26 & BoT-SORT to automatically add items to customer cart.
- **Role Based Access Control**: Separate interfaces for Customers, Shopkeepers, Inventory Managers, and Administrators.
- **Automated Notifications**: Real-time Telegram alerts for transactions, low stock warnings and inventory updates.
- **Receipt Generation**: Automatic generation of professional PDF receipts upon successful payment.
- **Inventory Management**: Manage stock availability, pricing, etc. with real-time sales metrics, and visual indicators for out-of-stock items.   
- **Payment Integration**: Seamless checkout experience integrated with the Razorpay API.
- **Custom-Trained Detection Model**: YOLO26 weights trained from scratch on a self-curated Indian grocery dataset.


<a id="screenshots--demo"></a>
## 🖼️ Screenshots & Demo

https://github.com/user-attachments/assets/4ba3bf44-2d12-4eff-b271-a9cc78d207c5

<p align="center">
  <img width="758" height="426" alt="Image" src="https://github.com/user-attachments/assets/69b66510-1076-4b95-aa2e-f4335b6656fa" />   <br><br>
   <img width="758" height="426" alt="Image" src="https://github.com/user-attachments/assets/0ce4f0ae-b51c-4133-b44e-dd5509de866f" />  <br><br>
   <img width="200" height="424" alt="Image" src="https://github.com/user-attachments/assets/12e726c0-ae68-4c4d-8628-7c7240f393a9" />  <br><br>
</p>

<a id="tech-stack"></a>
## 🛠️ Tech Stack
- **Computer Vision**: Ultralytics YOLO26 for object detection, BoT-SORT for tracking & OpenCV for frame processing
- **Backend**: FastAPI with Uvicorn, WebSockets
- **Frontend**: Tailwind CSS, Vanilla JavaScript & HTML5 with Jinja2
- **Database**: SQLite (store.db storing products, transactions, and users) with Pandas for processing
- **Integrations**: Razorpay API(test mode) for payments, Telegram Bot API for notifications, FPDF2 for receipt generation

<a id="dataset"></a>
## 📊 Dataset
The model was trained on a custom Indian Grocery Dataset hosted on Roboflow:
[Indian Grocery Management CV](https://app.roboflow.com/madhavs-workspace-507zc/indiangrocerymgmtcv/4), created with a combination of custom new images and forked public datasets, containing over 7,000+ images across 20 classes.

<a id="installation--setup"></a>
## ⚙️ Installation & Setup

1. **Clone & Install**:
   ```bash
   git clone https://github.com/m4dhv/optical_business_solutions_yolo26.git
   cd optical_business_solutions_yolo26
   pip install -r requirements.txt
   ```

2. **Configure**:
   Create a `.env` file from `.env.example` and add your credentials.

3. **Run**:
   ```bash
   python app.py
   ```
   Access at `http://localhost:8000`.

   ### Role Access
   - **Customer**: Self checkout billing interface
   - **Shopkeeper**: Access to past transactions and shopkeeper portal
   - **Inventory Manager**: Ability to update and manage inventory manually
   - **Administrator**: Privileges of all previous roles, along with user management and system settings

<a id="project-structure"></a>
## 📁 Project Structure

```
optical_business_solutions_yolo26/
├── app.py: FastAPI entry point and WebSocket handler
├── backend/
│   ├── vision_engine.py: YOLO inference, BoT-SORT tracking and OpenCV frame processing logic
│   ├── database_manager.py: SQLite CRUD operations and stock management
│   ├── checkout.py: Razorpay order creation and verification
│   └── utils.py: PDF receipt generation and Telegram bot notifications
├── templates/
│   ├── base.html: Common layout and navigation
│   ├── customer.html: Customer self-checkout UI
│   ├── shopkeeper.html: Shopkeeper dashboard and queue management
│   ├── admin.html: Admin panel for user and system settings management
│   ├── inventory.html: Inventory tracking and management through CRUD operations
│   └── checkout.html: Dynamic customer cart leading to Razorpay gateway
├── static/: Frontend assets, including style.css and store logo
└── weights/: YOLO26 model weights(.pt files)
```
<a id="acknowledgements"></a>
## 🙏 Acknowledgements

- [Ultralytics YOLO26](https://github.com/ultralytics/ultralytics) for the object detection framework.
- [Roboflow](https://roboflow.com/) for dataset hosting and annotation tooling.
- [FastAPI](https://fastapi.tiangolo.com/) for the backend framework.
- [Tailwind CSS](https://tailwindcss.com/) for frontend styling.
- [OpenCV](https://opencv.org/) for computer vision and image processing capabilities.
- [Telegram Bot API](https://core.telegram.org/bots/api) for real-time notifications and alerts.
- [Razorpay](https://razorpay.com/) for payment gateway integration.

<a id="license"></a>
## 📄 License
This project is licensed under the MIT License: [details](LICENSE).