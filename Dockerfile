FROM python:3.10-slim

WORKDIR /app

# We assume agy is installed on the host and we want to run this wrapper.
# If agy needs to be in the container, you would install it here.
# For now, we install the API requirements.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
