import jwt

import uvicorn
import models
import yfinance
from fastapi import FastAPI, Request, Depends, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import SessionLocal, engine
from pydantic import BaseModel 
from models import Stock, User
from sqlalchemy.orm import Session

import bcrypt
import json

app = FastAPI()

JWT_SECRET = 'jwtsecret'

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')

models.Base.metadata.create_all(bind=engine)
class StockRequest(BaseModel):
    symbol: str

class UserRequest(BaseModel):
    username: str
    password_hash: str 

def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def object_to_dict(obj):
    d = {}
    for column in obj.__table__.columns:
        d[column.name] = str(getattr(obj, column.name))
    return d

def toJSON(data):
    return JSONResponse(content=jsonable_encoder(data))


@app.post('/users')
async def create_user(user_request: UserRequest, db: Session = Depends(get_db)):
    user = User()
    user.username = user_request.username
    userpassword = user_request.username.encode('utf-8')
    user.password_hash = bcrypt.hashpw(userpassword, bcrypt.gensalt()).decode('utf-8')
    db.add(user)
    db.commit()


@app.post('/token')
async def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    username = form_data.username
    password = form_data.password
    user_obj = db.query(User).filter(User.username == username).first()
    
    # username 체크
    if not user_obj:
        return {'errer' : 'invalid credentials'}
    # password 체크
    if not bcrypt.checkpw(password.encode('utf-8'), user_obj.password_hash.encode('utf-8')):
        return {'errer' : 'invalid credentials'}
   
    token = jwt.encode(object_to_dict(user_obj), JWT_SECRET)
    return {'access_token':token, 'token_type':'bearer'}

@app.get("/")
async def index(token: str = Depends(oauth2_scheme)):
    return {"the_token": token}

def fetch_stock_data(id: int):
    db = SessionLocal()

    stock = db.query(Stock).filter(Stock.id == id).first()
    yahoo_data = yfinance.Ticker(stock.symbol)
    stock.ma200 = yahoo_data.info['twoHundredDayAverage']
    stock.ma50 = yahoo_data.info['fiftyDayAverage']
    stock.price = yahoo_data.info['previousClose']
    stock.forward_pe = yahoo_data.info['forwardPE']
    stock.forward_eps = yahoo_data.info['forwardEps']

    if yahoo_data.info['dividendYield'] is not None:
        stock.dividend_yield = yahoo_data.info['dividendYield'] * 100
    db.add(stock)
    db.commit()


@app.post("/stock")
async def create_stock(stock_request: StockRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):

    stock = Stock()
    stock.symbol = stock_request.symbol
    
    db.add(stock)
    db.commit()


    background_tasks.add_task(fetch_stock_data, stock.id)

    return {
        "code":"success",
        "msg":"stock created"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)