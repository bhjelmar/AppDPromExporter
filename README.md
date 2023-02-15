# AppDPromExporter

Scrape metrics from AppDynamics Controller and expose them for Prometheus consumption.

## Output

Metrics defined in `input/DefaultMapping.json` will be exposed on `http://localhost:9877` by default.

Metrics will be converted in the following way:
1. append the EntityType to the beginning
2. normalizing the metric path by replacing all non-alphanumeric characters with underscores
3. replacing stars with associated the label key
4. register the metric with its associated dynamic labels

### Example

`DefaultMapping.tsv`

| EntityType | MetricPath                                                                             | MetricName                 | Labels     |
|------------|----------------------------------------------------------------------------------------|----------------------------|------------|
| APM        | Overall Application Performance&#124;Average Response Time (ms)                        | Average Response Time (ms) |            |
| APM        | Overall Application Performance&#124;*&#124;Average Response Time (ms)                 | Average Response Time (ms) | tier	      |
| APM        | Application Infrastructure Performance&#124;\*&#124;Individual Nodes&#124;*&#124;Agent | App&#124;Availability      | tier,node	 |


Will register the following metrics
- `apm:overall_application_performance_average_response_time__ms_`
- `apm:overall_application_performance_TIER_average_response_time__ms_`
- `apm:application_infrastructure_performance_TIER_individual_nodes_NODE_agent_app_availability`

For each of these metrics, we will query AppDynamics:
- `apm:overall_application_performance_average_response_time__ms_`
  - one series returned for each application
    - `apm:overall_application_performance_average_response_time__ms_{application="foo"}`
    - `apm:overall_application_performance_average_response_time__ms_{application="bar"}`
- `apm:overall_application_performance_TIER_average_response_time__ms_`
  - one series returned for each application/tier combination
    - `apm:overall_application_performance_TIER_average_response_time__ms_`
      - `apm:overall_application_performance_TIER_average_response_time__ms_{application="foo",tier="bar"}`
      - `apm:overall_application_performance_TIER_average_response_time__ms_{application="foo",tier="baz"}`
- `apm:application_infrastructure_performance_TIER_individual_nodes_NODE_agent_app_availability`
  - one series returned for each application/tier/node combination
    - `apm:application_infrastructure_performance_TIER_individual_nodes_NODE_agent_app_availability`
      - `apm:application_infrastructure_performance_TIER_individual_nodes_NODE_agent_app_availability{application="foo",tier="bar",node="baz"}`
      - `apm:application_infrastructure_performance_TIER_individual_nodes_NODE_agent_app_availability{application="foo",tier="bar",node="qux"}`

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