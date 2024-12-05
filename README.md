# Overview

This project will save you time to build the basic ChatGPT `o1-preview` model

# How to use

* Please download the` main.zip` from the latest release version

* Unzip them into a folder
* put your own api key in  `config.json`
* Open the software and type `--help` or `--h` to see supported command

# Notes 

* If you want to use a different model, please change the `config.json`. 
  * **!!! For price field**: make sure you still put **3** number in the field. Put 0 in the middle field and enter:
    * First number for input token
    * Second number for output token
    * Since `o1-perview` have additional token which is `cached_token`, so we keep **3** number.