from locust import HttpUser, task, between

class WebsiteUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        # Register and login a user to get tokens
        self.client.post("/auth/register", json={"email": "locust@example.com", "password": "locustpassword"})
        response = self.client.post("/auth/login", data={"username": "locust@example.com", "password": "locustpassword"})
        self.access_token = response.json()["access_token"]

    @task
    def login(self):
        self.client.post("/auth/login", data={"username": "locust@example.com", "password": "locustpassword"})
