FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime
WORKDIR /app
COPY model_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY common common
COPY model_service model_service
EXPOSE 8001
# A single process owns the serial GPU queue; scale workers only with separate GPUs.
CMD ["uvicorn", "model_service.app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
