import os

import app_iot


if __name__ == '__main__':
    port = int(os.environ.get('PORT') or os.environ.get('IOT_APP_PORT', '5001'))
    host = os.environ.get('IOT_APP_HOST') or ('0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    app = app_iot.create_app()
    app.run(debug=False, host=host, port=port, use_reloader=False)
