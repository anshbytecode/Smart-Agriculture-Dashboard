from mangum import Mangum
from server.app import app

handler = Mangum(app)