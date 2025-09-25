from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, user_id, email, name, picture):
        self.id = user_id
        self.email = email
        self.name = name
        self.picture = picture
    
    def get_id(self):
        return str(self.id)