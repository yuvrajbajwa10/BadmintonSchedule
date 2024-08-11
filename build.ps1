# Prompt the user for the tag number
$tagNumber = Read-Host "Enter the tag number:"
$imageName = "badminton_schedule"
$dockerRegistryURL = "registry.bajwa.fun"
$fullImageName = "${dockerRegistryURL}/${imageName}:${tagNumber}"

# Update the local git repository
try {
    git pull
} catch {
    Write-Error "Git pull failed. Exiting script."
    exit 1
}

# Build the Docker image
docker build -t $fullImageName .

# Push the Docker image to the registry
docker push $fullImageName

# Clean up the build machine
docker rmi $fullImageName
