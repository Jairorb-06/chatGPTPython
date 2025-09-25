from app import create_app

app = create_app()

# comentar para desplegar
if __name__ == '__main__':
    # app.run(debug=True,  port=8001)
    app.run(debug=True, host='127.0.0.1', port=8001)
