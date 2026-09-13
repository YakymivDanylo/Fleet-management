# Runs a SonarQube analysis of this project via the containerized scanner CLI.
# Requires: Docker running, SonarQube container up (docker compose -f config/docker-compose.yml up -d sonarqube),
# and SONAR_TOKEN set in the environment (generate it once at http://localhost:9000/account/security).

param(
    [string]$SonarToken = $env:SONAR_TOKEN
)

if (-not $SonarToken) {
    Write-Error "SONAR_TOKEN is not set. Run: `$env:SONAR_TOKEN = '<your token>'"
    exit 1
}

docker run --rm `
    -e SONAR_HOST_URL="http://host.docker.internal:9000" `
    -e SONAR_TOKEN=$SonarToken `
    -v "${PWD}:/usr/src" `
    -w /usr/src `
    sonarsource/sonar-scanner-cli
