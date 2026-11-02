"""Compatibility entry point for the Random Forest website."""
import argparse
from app import ROOT, create_app, load_model
from open_website import main, website_ready, port_in_use

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('variant', choices=['rf'])
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.serve:
        from waitress import serve
        serve(create_app(), host='127.0.0.1', port=8001, threads=4)
    elif args.check:
        load_model(ROOT / 'models/model.joblib')
        print('Matching server ready:', website_ready())
        print('Port in use:', port_in_use())
    else:
        main()
