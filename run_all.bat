@echo off
REM Chaine complete : ETL -> entrainement -> anomalies -> tests -> API (http://127.0.0.1:5050)
cd /d "%~dp0"
set PYTHONPATH=src
python -m aeroops.etl || goto :error
python -m aeroops.train || goto :error
python -m aeroops.anomalies || goto :error
python -m pytest -q > reports\test_results.txt
type reports\test_results.txt
echo Tableau de bord : http://127.0.0.1:5050  (Ctrl+C pour arreter)
python -m aeroops.api
goto :eof
:error
echo Une etape a echoue : voir les messages ci-dessus.
exit /b 1
