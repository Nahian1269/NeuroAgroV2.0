import os

import app_iot


if __name__ == '__main__':
    port = int(os.environ.get('IOT_APP_PORT', '5001'))
    app = app_iot.create_app()
    app.run(debug=False, host='127.0.0.1', port=port, use_reloader=False)
