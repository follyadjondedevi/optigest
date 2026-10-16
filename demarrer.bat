@echo off
echo.
echo  ==============================
echo   OptiGest - Version Web
echo  ==============================
echo.
echo  Installation des dependances...
py -m pip install flask --quiet
echo.
echo  Demarrage du serveur...
echo.
echo  Ouvrez votre navigateur sur : http://localhost:5000
echo  Sur telephone (meme WiFi)   : http://[IP-du-PC]:5000
echo.
echo  Pour arreter : appuyez sur CTRL+C
echo.
py app.py
pause
