from seleniumwire.utils import decode

import sys
import re
import traceback


def expose_game_data(request, response):
    """
    Intercept the 'web.[hash].js' script from colonist.io/dist/ and inject references
    to `window.gameManager`, `window.uiGameManager`, etc.
    """
    try:
        if response and response.status_code == 200:
            # We only want to modify the main colonist dist scripts (web.xxxxx.js).
            if ("colonist.io/dist/" in request.url and
                    re.search(r'/web\.[0-9a-z]+\.(js|js\?.*)$', request.url)):

                # Decode the response body (handle compression if needed).
                original_body = decode(
                    response.body,
                    response.headers.get('Content-Encoding', 'identity')
                )
                body_str = original_body.decode('utf-8', errors='ignore')

                # Inject our modifications:
                new_body_str = body_str.replace(
                    "this.forceHideAds=!1,this.uiGameManager=e,",
                    "this.forceHideAds=1,window.uiGameManager=e,this.uiGameManager=e,",
                    1  # replace only the first match
                )
                new_body_str = new_body_str.replace("this.endGameState=t,this.isReplayAvailable=i,",
                    "this.endGameState=t,this.isReplayAvailable=i,window.endGameState=t,",
                    1  # replace only the first match
                )

                # Re-encode and remove Content-Encoding so the browser sees it uncompressed.
                response.body = new_body_str.encode('utf-8')
                if 'Content-Encoding' in response.headers:
                    del response.headers['Content-Encoding']

                # Update content length
                response.headers['Content-Length'] = str(len(response.body))
                print('JS Intercepted...')
                print(len(body_str))
                print(len(new_body_str))

    except Exception as e:
        # Log any exceptions
        print(f"Interceptor error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)