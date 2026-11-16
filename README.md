# Work Log

A small, self-hosted work-hours calendar. It uses Python's standard library and SQLite, so it has no package installation step and no external service requirement.

## Build and run on Windows

On a Windows computer with Python 3 installed, double-click `build_windows.bat` (or run it from Command Prompt). It installs PyInstaller and creates `dist\WorkLog.exe`. Copy the whole `dist` folder to the Windows computer where you want to use Work Log, then double-click `WorkLog.exe`; it opens the app in your browser. Keep the window open while using it.

The database is stored in `dist\data\worklog.sqlite3`, beside the executable, and annual PDFs are saved under `dist\Year Report`. If the project already has a database when you build, the script copies it into `dist\data`.

The executable must be built on Windows because PyInstaller does not cross-compile Windows executables from Linux.

## Run on Ubuntu

```sh
cd ~/worklog
./run.sh
```

The app listens on `127.0.0.1:8000` on the server. Keep it running in that terminal (or run it in `tmux`). To stop it, press `Ctrl+C`.

On your own computer, open a second terminal and create an SSH tunnel:

```sh
ssh -L 8000:localhost:8000 your-user@your-server
```

Keep the SSH session open and visit <http://localhost:8000> in your computer's browser. The app itself does not need a browser or desktop on Ubuntu.

If local port 8000 is already in use, use another local port on the left side, for example `ssh -L 8080:localhost:8000 your-user@your-server`, then visit <http://localhost:8080>.

## Use

- Click a date to add a record; for repeated work, choose a start and end date to create the same record for each day in that inclusive range. Click an existing record on the calendar to edit or delete it.
- New records default to 12 hours per day.
- Each record has a date, project number and name, location, hours, and note. More than one project record can be added to a day if needed.
- Use **Statistics** to view weekly, monthly, or yearly totals, hours grouped by project, and counts of records whose notes contain “relay”.
- **Export CSV** downloads the records for the selected period as a spreadsheet-friendly file.
- **Annual PDF** creates and downloads a year report for the year selected by the date field. The server also saves it as `Year Report/<year>/<year>worklog.pdf`. It includes an annual overview, monthly analyses and charts, and a calendar for each month.

## Data and moving to another machine

The database is `data/worklog.sqlite3`. Stop the app before copying the database so the copy is consistent. To move the app and its history, copy the whole `worklog` directory, including `data/worklog.sqlite3`, to the other machine. Python 3 is the only runtime requirement. You can also put the database elsewhere by setting `WORKLOG_DB=/path/to/worklog.sqlite3` before running `./run.sh`.

Keep the app on loopback (`127.0.0.1`) and use the SSH tunnel for remote access. It has no user login, so do not expose its port directly to the network.
