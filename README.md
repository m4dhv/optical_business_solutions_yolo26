# Optical Business Solutions (Self Checkout and Inventory Management using YOLO26)

CV Based Self checkout billing system and inventory management system using computer vision via YOLO26, a FastAPI backend and a Tailwind CSS/HTML frontend. 

## Core Features

- **AI-Powered Billing**: Real-time object detection and tracking using YOLO26 to automatically add items to the customer's cart.
- **Role-Based Access Control**: Separate interfaces for Customers, Shopkeepers, Inventory Managers, and Administrators.
- **Payment Integration**: Seamless checkout experience integrated with the Razorpay API.
- **Automated Notifications**: Real-time Telegram alerts for transactions and low-stock warnings.
- **Receipt Generation**: Automatic generation of professional PDF receipts upon successful payment.
- **Inventory Management**: Role based pages with real-time sales metrics and visual indicators for out-of-stock items.

## Tech Stack

- **Backend**: FastAPI
- **Computer Vision**: Ultralytics YOLO26
- **Database**: SQLite
- **Frontend**: Tailwind CSS/HTML
- **Payments**: Razorpay
- **Notifications**: Telegram Bot API

## Dataset
The model was trained on a custom Indian Grocery Dataset hosted on Roboflow:
[Indian Grocery Management CV](https://app.roboflow.com/madhavs-workspace-507zc/indiangrocerymgmtcv/4)
Created by forking images from multiple existing datasets from Roboflow and capturing custom images.

## Installation & Setup

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
- **Customer**: Automatic billing.
- **Shopkeeper**: Transactions.
- **Admin**: Full control.

## Project Structure

- `app.py`: FastAPI entry point and WebSocket handler.
- `backend/`:
  - `vision_engine.py`: YOLO inference and frame annotation logic.
  - `database_manager.py`: SQLite CRUD operations and stock management.
  - `checkout.py`: Razorpay order creation and verification.
  - `utils.py`: PDF receipt generation and Telegram bot notifications.
- `templates/`:
  - `base.html`: Common layout and navigation.
  - `customer.html`: Customer self-checkout UI.
  - `shopkeeper.html`: Shopkeeper dashboard and queue management.
  - `admin.html`: Admin panel for user and system management.
  - `inventory.html`: Inventory tracking and sorting.
  - `checkout.html`: Razorpay payment integration page.
- `static/`: Frontend assets including style.css and store logo.
- `weights/`:YOLO26 model weights (.pt files).

