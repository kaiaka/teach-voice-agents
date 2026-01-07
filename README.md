# Setup
First time setup on your machine.




### ( 1 ) Create virtual python environment
Create python environment. Make sure to use Python version < 3.13 for compability reasons (e.g. with pyenv).

#### Activate / check python version
```bash
pyenv versions
pyenv local 3.12.8
python --version     
```

#### Install PortAudio (global)
```bash
brew install portaudio  # on macOS
```

#### Create virtual environment
```bash
create venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
``` 




### ( 2 ) Create .env config file
There's a env.example file in the top folder. 
Copy as '.env' and add information such as your OPENAI API key.

