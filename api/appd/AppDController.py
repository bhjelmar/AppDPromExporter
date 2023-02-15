from uplink import Body, Consumer, Path, Query, error_handler, get, headers, params, post


class ApiError(Exception):
    pass


def raise_api_error(exc_type, exc_val, exc_tb):
    raise ApiError(exc_val)


@error_handler(raise_api_error)
class AppdController(Consumer):
    """Minimal python client for the AppDynamics API"""

    jsessionid: str = None
    xcsrftoken: str = None

    @params({"action": "login"})
    @get("/controller/auth")
    def login(self):
        """Verifies Login Success"""

    @params({"output": "json"})
    @get("/controller/restui/applicationManagerUiBean/getApplicationsAllTypes")
    def getApplicationsAllTypes(self):
        """Retrieves all types of Applications"""

    @params({"output": "json"})
    @get("/controller/rest/applications")
    def getApmApplications(self):
        """Retrieves Applications"""

    @params({"output": "json"})
    @get("/controller/rest/applications/{applicationID}/metric-data")
    def getMetricData(
            self,
            applicationID: Path,
            metric_path: Query("metric-path"),
            rollup: Query("rollup"),
            time_range_type: Query("time-range-type"),
            duration_in_mins: Query("duration-in-mins"),
            start_time: Query("start-time"),
            end_time: Query("end-time"),
    ):
        """Retrieves Metrics"""

    @params({"output": "json"})
    @get("/controller/restui/eumApplications/getAllEumApplicationsData")
    def getEumApplications(self, timeRange: Query("time-range")):
        """Retrieves all Eum Applications"""

    @params({"output": "json"})
    @get("/controller/restui/eumApplications/getAllMobileApplicationsData")
    def getMRUMApplications(self, timeRange: Query("time-range")):
        """Retrieves all Mrum Applications"""
