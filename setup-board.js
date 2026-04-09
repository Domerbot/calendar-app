const GITHUB_TOKEN = 'your_token_here';
const GITHUB_USERNAME = 'Domerbot';
const PROJECT_NUMBER = 1;

const tasks = [
  // FOUNDATIONS
  "Set up project folder structure",
  "Install Git and initialise repository",
  "Create README file",
  "Push first commit to GitHub",
  
  // FRONTEND
  "Create basic HTML page with calendar layout",
  "Add CSS styling - mobile friendly",
  "Create Today view - shows today's events",
  "Create Upcoming view - shows next 2 weeks",
  "Create Countdown feature - days until key events",
  "Add form to create new events",
  "Add ability to delete events",
  
  // BACKEND
  "Set up Python FastAPI backend",
  "Create endpoint to get all events",
  "Create endpoint to add new event",
  "Create endpoint to delete event",
  "Connect frontend to backend",
  
  // DATA
  "Set up SQLite database",
  "Create events table",
  "Test saving and retrieving events",
  
  // AI FEATURE
  "Connect OpenAI API",
  "Build weekly summary feature",
  "Display AI summary on dashboard",
  
  // FINISHING
  "Test on mobile browser",
  "Share with Julie and get feedback",
  "Deploy app so it works on any device"
];

async function getProjectId() {
  const query = `
    query {
      user(login: "${GITHUB_USERNAME}") {
        projectV2(number: ${PROJECT_NUMBER}) {
          id
        }
      }
    }
  `;
  
  const response = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${GITHUB_TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ query })
  });
  
  const data = await response.json();
  return data.data.user.projectV2.id;
}

async function addTask(projectId, title) {
  const mutation = `
    mutation {
      addProjectV2DraftIssue(input: {
        projectId: "${projectId}"
        title: "${title}"
      }) {
        projectItem {
          id
        }
      }
    }
  `;
  
  await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${GITHUB_TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ query: mutation })
  });
  
  console.log(`✅ Added: ${title}`);
}

async function main() {
  console.log('🚀 Setting up your project board...');
  const projectId = await getProjectId();
  
  for (const task of tasks) {
    await addTask(projectId, task);
  }
  
  console.log('🎉 Done! Check your GitHub Projects board.');
}

main();