FROM python:3.11

# Install requirements
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Copy app
COPY . .

# Run it
CMD [ "python", "main.py" ]