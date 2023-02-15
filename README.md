# AppDPromExporter

Scrape metrics from AppDynamics Controller and expose them for Prometheus consumption.

## Usage

Run from source

1. `git clone https://github.com/bhjelmar/AppDPromExporter.git`
2. `cd AppDPromExporter`
3. `poetry install`
4. `poetry shell`
5. `python3 main.py -j DefaultJob -m DefaultMapping`

```
Usage: main.py [OPTIONS]

Options:
  -c, --concurrent-connections INTEGER
  -d, --debug
  -p, --port INTEGER
  -j, --job-file TEXT
  -m, --mapping-file TEXT
  --help                          Show this message and exit.
```

Options `--job-file` and `--mapping-file` will default to `DefaultJob` and `DefaultMapping` respectively.

All Job and Mapping files must be contained in `AppDPromExprter/input` and `config_assessment_tool/resources/thresholds`. They are to be referenced by name file name (excluding .json), not full path.

## JobFile Settings

[DefaultJob.json](https://github.com/bhjelmar/AppDPromExporter/blob/master/input/DefaultJob.json) defines a number of optional configurations.

- verifySsl
  - enabled by default, disable it to disable SSL cert checking (equivalent to `curl -k`)
- useProxy
  - As defined above under [Proxy Support](https://github.com/bhjelmar/AppDPromExporter#proxy-support), enable this to use a configured proxy
- applicationFilter
  - Three filters are available, one for `apm`, `mrum`, and `brum`
  - The filter value accepts any valid regex, set to `.*` by default
  - Set the value to null to filter out all applications for the set type
- refreshIntervalMinutes
  - Frequency of data pull from AppDynamics Controller
  - This will also be the lookback period for metrics

## Proxy Support

Support for plain HTTP proxies and HTTP proxies that can be upgraded to HTTPS via the HTTP CONNECT method is provided by enabling the `useProxy` flag in a given job file. Enabling this flag will cause
the backend to use the proxy specified from environment variables: HTTP_PROXY, HTTPS_PROXY, WS_PROXY or WSS_PROXY (all are case insensitive). Proxy credentials are given from ~/.netrc file if present.
See aiohttp.ClientSession [documentation](https://docs.aiohttp.org/en/stable/client_advanced.html#proxy-support) for more details.