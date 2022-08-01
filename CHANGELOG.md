# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

## [1.5.0] - tbd

### Update notes

This update will temporarily remove all contacts and wars. After you completed the installation, please manually trigger the update task to fetch contacts and wars again (or wait for it to run from schedule):

```bash
celery -A myauth call standingssync.tasks.run_regular_sync
```

### Changed

- Migrated proprietary EveEntity to EveUniverse's EveEntity to enable ID to Name resolution

### Fixed

- Fix: Not all active wars are shown in the app

## [1.4.1] - 2022-07-29

### Added

- Show allies on EveWar admin site

### Fixed

- Search on EveWar page does not work

## [1.4.0] - 2022-07-20

### Added

- Show entities and wars on admin site

## [1.3.1] - 2022-06-18

### Changed

- Add wheel to PyPI deployment
- Switch to local swagger spec file
- Add tests to distribution package

## [1.3.0] - 2022-03-02

### Changed

- Remove support for Python 3.6
- Remove support for Django 3.1

### Fixed

- SessionMiddleware() in tests requires additional parameter

### Changed

## [1.2.2] - 2022-03-01

### Changed

- Remove deprecations that are being remove in Django 4

## [1.2.1] - 2021-10-28

### Changed

- Added CI tests for AA 2.9+ (Python 3.7+, Django 3.2), removed CI tests for AA < 2.9 (Python 3.6, Django 3.1)

## [1.2.0] - 2021-08-05

### Added

- Status indicator for sync ok on admin site for both managers and characters

## [1.2.0b4] - 2021-03-01

### Added

- Ability to also sync war targets to alt characters. Please see settings on how to activate this feature. [#5](https://gitlab.com/ErikKalkoken/aa-standingssync/-/issues/5)

### Changed

- Remove support for Django 2
- UI refresh
- Migrated to allianceauth-app-utils
- Codecov integration

## [1.1.4] - 2020-10-09

### Changed

- Changed logo to better reflect what this app does
- Now logs to to extensions logger
- Add improved logging for standing rejections
- Added tests

### Fixed

- Minor fixes

## [1.1.3] - 2020-09-24

### Changed

- Added Django 3 to test suite
- Reformatted with new Black version

## [1.1.2] - 2020-07-04

### Changed

- Added Black as mandatory linter
- Added support for django-esi 2.x and backwards compatibility for 1.x

## [1.1.1] - 2020-06-30

### Changed

- Update to Font Awesome v5. Thank you Peter Pfeufer for your contribution!

## [1.1.0] - 2020-05-28

### Changed

- Drops support for Python 3.5
- Updated dependency for django-esi to exclude 2.0
- Added timeout to ESI requests

## [1.0.4] - 2020-04-19

### Fixed

- New attempt to reduce the memory leaks in celery workers

## [1.0.3] - 2020-04-12

### Changed

- Sync status now updated at the end of the process, not at the beginning

### Fixed

- Corrected required permission for adding sync managers
- Minor bugfixes
- Improved test coverage

## [1.0.2] - 2020-02-28

### Added

- Version number for this app now shown on admin site

### Fixed

- Bug: Standing value was sometimes not synced correctly for contacts

## [1.0.1] - 2019-12-19

### Changed

- Improved error handling of contacts sync process
- Improved layout of messages

## [1.0.0] - 2019-10-02

### Added

- First release
