// get the ninja-keys element
const ninja = document.querySelector('ninja-keys');

// add the home and posts menu items
ninja.data = [{
    id: "nav-about",
    title: "about",
    section: "Navigation",
    handler: () => {
      window.location.href = "/";
    },
  },{id: "nav-past-workshops",
          title: "Past workshops",
          description: "A collection of workshops I have organised in the past.",
          section: "Navigation",
          handler: () => {
            window.location.href = "/workshops/";
          },
        },{id: "nav-for-review-requests",
          title: "For review requests",
          description: "",
          section: "Navigation",
          handler: () => {
            window.location.href = "/review/";
          },
        },{id: "nav-cv",
          title: "CV",
          description: "",
          section: "Navigation",
          handler: () => {
            window.location.href = "/cv/";
          },
        },{id: "projects-bes-39-festival-of-ecology-2020",
          title: 'BES&amp;#39; Festival of Ecology 2020',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/BES2020/";
            },},{id: "projects-university-of-antwerp-2023",
          title: 'University of Antwerp 2023',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/Antwerp/";
            },},{id: "projects-uppsala-university-2024",
          title: 'Uppsala University 2024',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/Uppsala/";
            },},{id: "projects-international-research-school-in-applied-ecology-2021",
          title: 'International Research School in Applied Ecology 2021',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/IRSAE2024/";
            },},{id: "projects-generalised-linear-models-with-physalia",
          title: 'Generalised Linear Models with Physalia',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/GLMsPhy/";
            },},{id: "projects-generalised-linear-latent-variable-models-with-physalia",
          title: 'Generalised Linear Latent Variable Models with Physalia',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/GLLVMsPhy/";
            },},{id: "projects-norwegian-oikos-2025",
          title: 'Norwegian Oikos 2025',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/NOF2025/";
            },},{id: "projects-summer-school-in-model-based-multivariate-analysis-for-ecologists",
          title: 'Summer School in Model-based multivariate analysis for ecologists',
          description: "",
          section: "Projects",handler: () => {
              window.location.href = "/projects/SSMA/";
            },},{
      id: 'light-theme',
      title: 'Change theme to light',
      description: 'Change the theme of the site to Light',
      section: 'Theme',
      handler: () => {
        setThemeSetting("light");
      },
    },
    {
      id: 'dark-theme',
      title: 'Change theme to dark',
      description: 'Change the theme of the site to Dark',
      section: 'Theme',
      handler: () => {
        setThemeSetting("dark");
      },
    },
    {
      id: 'system-theme',
      title: 'Use system default theme',
      description: 'Change the theme of the site to System Default',
      section: 'Theme',
      handler: () => {
        setThemeSetting("system");
      },
    },];
