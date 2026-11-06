from flask import Blueprint, request, jsonify
from models import Stock, UserStock
from extensions import db

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/track', methods=['POST'])
def track_stock():
    data = request.get_json()
    user_id = data.get('user_id')
    symbol = data.get('symbol')
    shares = data.get('shares')

    stock = Stock.query.filter_by(symbol=symbol).first()
    if not stock:
        stock = Stock(symbol=symbol)
        db.session.add(stock)

    user_stock = UserStock.query.filter_by(user_id=user_id, stock_id=stock.id).first()
    if user_stock:
        user_stock.shares = shares
    else:
        user_stock = UserStock(user_id=user_id, stock_id=stock.id, shares=shares)
        db.session.add(user_stock)

    db.session.commit()

    return jsonify({'message': 'Stock tracked successfully'}), 200

@stock_bp.route('/portfolio/<int:user_id>', methods=['GET'])
def get_portfolio(user_id):
    user_stocks = UserStock.query.filter_by(user_id=user_id).all()
    portfolio = []

    for user_stock in user_stocks:
        stock = Stock.query.get(user_stock.stock_id)
        portfolio.append({
            'symbol': stock.symbol,
            'shares': user_stock.shares,
            'current_price': stock.current_price
        })

    return jsonify(portfolio)